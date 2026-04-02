#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoEdit Generator - Автоматический создатель видеороликов из фотографий и видео под музыку.

Программа создает видеоролики из фотографий и коротких видео, синхронизируя их с битами музыки.
Использует библиотеки: librosa (анализ битов), moviepy (монтаж видео), tkinter (GUI).

Автор: AI Assistant
Версия: 1.0
Требования: Python 3.8+, ffmpeg
"""

import os
import sys
import threading
import random
import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

# Проверка зависимостей при запуске
REQUIRED_LIBRARIES = ['librosa', 'moviepy', 'numpy']

def check_dependencies():
    """Проверяет наличие всех необходимых библиотек."""
    missing = []
    for lib in REQUIRED_LIBRARIES:
        try:
            __import__(lib)
        except ImportError:
            missing.append(lib)
    
    if missing:
        print("Отсутствуют необходимые библиотеки:")
        for lib in missing:
            print(f"  - {lib}")
        print("\nУстановите их командой:")
        print(f"pip install {' '.join(missing)}")
        return False
    return True

# Импортируем библиотеки после проверки
import numpy as np
import librosa
from moviepy.editor import (
    VideoFileClip, ImageClip, concatenate_videoclips, 
    AudioFileClip, CompositeVideoClip, ColorClip
)
from moviepy import vfx
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


class BeatDetector:
    """Класс для детекции битов в аудиофайле."""
    
    def __init__(self, audio_path: str):
        self.audio_path = audio_path
        self.bpm = None
        self.beat_times = []
        self.duration = 0
    
    def detect_beats(self, progress_callback=None) -> Tuple[List[float], float, float]:
        """
        Анализирует аудиофайл и возвращает временные метки битов.
        
        Returns:
            Tuple[List[float], float, float]: (beat_times, bpm, duration)
        """
        if progress_callback:
            progress_callback(0, "Загрузка аудиофайла...")
        
        # Загружаем аудио с помощью librosa
        y, sr = librosa.load(self.audio_path, sr=None)
        self.duration = len(y) / sr
        
        if progress_callback:
            progress_callback(30, "Вычисление темпа (BPM)...")
        
        # Вычисляем BPM
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        self.bpm = float(tempo)
        
        if progress_callback:
            progress_callback(60, "Преобразование фреймов во время...")
        
        # Преобразуем фреймы битов во временные метки (секунды)
        self.beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
        
        # Проверяем, найдены ли биты
        if len(self.beat_times) == 0:
            if progress_callback:
                progress_callback(100, "Биты не найдены, используем равномерную сетку")
            # Создаем равномерную сетку каждые 2 секунды
            self.beat_times = [i * 2.0 for i in range(int(self.duration / 2.0) + 1)]
        
        if progress_callback:
            progress_callback(100, f"Анализ завершен! Найдено {len(self.beat_times)} битов")
        
        return self.beat_times, self.bpm, self.duration


class TimelineBuilder:
    """Класс для построения таймлайна видео."""
    
    def __init__(self, media_files: List[str], beat_times: List[float], 
                 video_duration: float, beats_per_clip: int = 1):
        self.media_files = media_files
        self.beat_times = beat_times
        self.video_duration = min(video_duration, beat_times[-1] if beat_times else video_duration)
        self.beats_per_clip = beats_per_clip
        self.timeline = []  # Список кортежей (media_file, start_time, end_time)
    
    def build(self) -> List[Dict[str, Any]]:
        """
        Строит таймлайн, распределяя медиафайлы по кадрам.
        
        Returns:
            List[Dict]: Список кадров с информацией о файле, времени начала и конца
        """
        timeline = []
        
        # Определяем длительность каждого кадра на основе битов
        clip_durations = []
        current_time = 0.0
        
        for i in range(0, len(self.beat_times) - 1, self.beats_per_clip):
            if current_time >= self.video_duration:
                break
            
            # Конец текущего кадра - через N битов
            end_beat_idx = min(i + self.beats_per_clip, len(self.beat_times) - 1)
            end_time = self.beat_times[end_beat_idx]
            
            if end_time > self.video_duration:
                end_time = self.video_duration
            
            duration = end_time - current_time
            if duration > 0:
                clip_durations.append(duration)
            
            current_time = end_time
        
        # Если биты не найдены или их мало, используем равномерное распределение
        if not clip_durations:
            num_clips = max(1, len(self.media_files))
            avg_duration = self.video_duration / num_clips
            clip_durations = [avg_duration] * num_clips
        
        # Распределяем медиафайлы по таймлайну
        current_time = 0.0
        file_index = 0
        
        for duration in clip_durations:
            if current_time >= self.video_duration:
                break
            
            # Выбираем файл (циклически, если файлов меньше чем нужно)
            media_file = self.media_files[file_index % len(self.media_files)]
            file_index += 1
            
            end_time = min(current_time + duration, self.video_duration)
            
            timeline.append({
                'file': media_file,
                'start_time': current_time,
                'end_time': end_time,
                'duration': end_time - current_time,
                'is_video': media_file.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))
            })
            
            current_time = end_time
        
        self.timeline = timeline
        return timeline


class ClipProcessor:
    """Класс для обработки отдельных клипов (фото и видео)."""
    
    @staticmethod
    def get_random_color_filter():
        """Возвращает случайный цветовой фильтр."""
        filters = [
            ('warm', lambda clip: vfx.colorx(clip, 1.2)),  # Тёплый
            ('cool', lambda clip: vfx.colorx(clip, 0.9)),  # Холодный
            ('sepia', lambda clip: vfx.lum_contrast(clip, lum=1.2, cont=1.1)),  # Сепия
            ('normal', lambda clip: clip)  # Без изменений
        ]
        return random.choice(filters)
    
    @staticmethod
    def apply_ken_burns_effect(clip: ImageClip, duration: float) -> CompositeVideoClip:
        """
        Применяет эффект Кен Бёрнс к фотографии (медленное масштабирование/панорамирование).
        
        Args:
            clip: Исходный ImageClip
            duration: Длительность эффекта в секундах
            
        Returns:
            CompositeVideoClip с применённым эффектом
        """
        # Случайное направление и масштаб
        scale_start = 1.0
        scale_end = random.uniform(1.05, 1.15)
        
        # Случайное смещение для панорамирования
        max_shift_x = int(clip.w * 0.1)
        max_shift_y = int(clip.h * 0.1)
        
        shift_x = random.randint(-max_shift_x, max_shift_x)
        shift_y = random.randint(-max_shift_y, max_shift_y)
        
        # Создаём функцию анимации
        def make_frame(t):
            progress = t / duration if duration > 0 else 0
            current_scale = scale_start + (scale_end - scale_start) * progress
            current_shift_x = int(shift_x * progress)
            current_shift_y = int(shift_y * progress)
            
            # Получаем кадр и применяем трансформации
            frame = clip.get_frame(t)
            # Примечание: для полноценного эффекта нужно использовать resize и crop
            # Здесь упрощённая версия
            return frame
        
        # Применяем эффект масштабирования через resize
        resized_clip = clip.resize(lambda t: scale_start + (scale_end - scale_start) * (t / duration if duration > 0 else 0))
        
        # Центрируем и обрезаем до исходного размера
        final_clip = resized_clip.crop(
            x_center=resized_clip.w // 2 + shift_x // 2,
            y_center=resized_clip.h // 2 + shift_y // 2,
            width=clip.w,
            height=clip.h
        )
        
        return final_clip.set_duration(duration)
    
    @staticmethod
    def process_image(image_path: str, duration: float, target_size: Tuple[int, int] = (1920, 1080)) -> VideoFileClip:
        """
        Обрабатывает изображение: применяет эффект Кен Бёрнс и цветовой фильтр.
        
        Args:
            image_path: Путь к изображению
            duration: Длительность показа в секундах
            target_size: Целевое разрешение (ширина, высота)
            
        Returns:
            VideoFileClip с применёнными эффектами
        """
        # Создаём ImageClip
        clip = ImageClip(image_path).set_duration(duration)
        
        # Масштабируем до целевого разрешения, сохраняя пропорции
        clip = clip.resize(height=target_size[1])
        if clip.w < target_size[0]:
            clip = clip.resize(width=target_size[0])
        
        # Обрезаем до целевого разрешения
        clip = clip.crop(x_center=clip.w // 2, y_center=clip.h // 2, 
                        width=target_size[0], height=target_size[1])
        
        # Применяем эффект Кен Бёрнс
        clip = ClipProcessor.apply_ken_burns_effect(clip, duration)
        
        # Применяем случайный цветовой фильтр
        filter_func = ClipProcessor.get_random_color_filter()[1]
        clip = filter_func(clip)
        
        return clip
    
    @staticmethod
    def process_video(video_path: str, duration: float, target_size: Tuple[int, int] = (1920, 1080)) -> VideoFileClip:
        """
        Обрабатывает видео: обрезает/ускоряет/замедляет до нужной длительности, добавляет эффекты.
        
        Args:
            video_path: Путь к видеофайлу
            duration: Целевая длительность в секундах
            target_size: Целевое разрешение (ширина, высота)
            
        Returns:
            VideoFileClip с применёнными эффектами
        """
        # Загружаем видео
        clip = VideoFileClip(video_path)
        
        # Случайное ускорение/замедление (0.8x - 1.2x)
        speed_factor = random.uniform(0.8, 1.2)
        clip = clip.fx(vfx.speedx, speed_factor)
        
        # Масштабируем до целевого разрешения
        clip = clip.resize(height=target_size[1])
        if clip.w < target_size[0]:
            clip = clip.resize(width=target_size[0])
        
        # Обрезаем до целевого разрешения
        clip = clip.crop(x_center=clip.w // 2, y_center=clip.h // 2,
                        width=target_size[0], height=target_size[1])
        
        # Применяем случайный цветовой оттенок
        filter_func = ClipProcessor.get_random_color_filter()[1]
        clip = filter_func(clip)
        
        # Обрезаем или зацикливаем до нужной длительности
        if clip.duration > duration:
            clip = clip.subclip(0, duration)
        elif clip.duration < duration and clip.duration > 0:
            # Зацикливаем видео
            clip = clip.loop(duration=duration)
        
        return clip.set_duration(duration)


class TransitionManager:
    """Класс для управления переходами между клипами."""
    
    TRANSITION_TYPES = ['fade', 'slide', 'dissolve']
    
    @staticmethod
    def get_random_transition(clip: VideoFileClip, transition_duration: float = 0.2) -> VideoFileClip:
        """
        Применяет случайный переход к клипу.
        
        Args:
            clip: Исходный клип
            transition_duration: Длительность перехода в секундах
            
        Returns:
            VideoFileClip с применённым переходом
        """
        transition_type = random.choice(TransitionManager.TRANSITION_TYPES)
        
        if transition_type == 'fade':
            # Fade in/out
            clip = clip.fadein(transition_duration).fadeout(transition_duration)
        elif transition_type == 'slide':
            # Slide effect (сдвиг)
            clip = clip.slide_in(transition_duration)
        elif transition_type == 'dissolve':
            # Dissolve (crossfade)
            clip = clip.crossfadein(transition_duration)
        
        return clip


class VideoRenderer:
    """Класс для рендеринга финального видео."""
    
    def __init__(self, output_path: str, audio_path: str):
        self.output_path = output_path
        self.audio_path = audio_path
        self.target_size = (1920, 1080)
        self.fps = 30
    
    def render(self, timeline: List[Dict[str, Any]], 
               progress_callback=None) -> bool:
        """
        Рендерит финальное видео из таймлайна.
        
        Args:
            timeline: Список кадров от TimelineBuilder
            progress_callback: Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True если успешно, False иначе
        """
        try:
            processed_clips = []
            total_clips = len(timeline)
            
            # Обрабатываем каждый кадр
            for i, frame in enumerate(timeline):
                if progress_callback:
                    progress_callback(int((i / total_clips) * 70), 
                                    f"Обработка кадров {i+1}/{total_clips}...")
                
                try:
                    if frame['is_video']:
                        clip = ClipProcessor.process_video(
                            frame['file'], 
                            frame['duration'],
                            self.target_size
                        )
                    else:
                        clip = ClipProcessor.process_image(
                            frame['file'],
                            frame['duration'],
                            self.target_size
                        )
                    
                    # Добавляем переход (кроме последнего клипа)
                    if i < total_clips - 1:
                        clip = TransitionManager.get_random_transition(clip)
                    
                    processed_clips.append(clip)
                    
                except Exception as e:
                    print(f"Ошибка обработки файла {frame['file']}: {e}")
                    continue
            
            if not processed_clips:
                raise ValueError("Не удалось обработать ни один файл")
            
            if progress_callback:
                progress_callback(75, "Склейка клипов...")
            
            # Склеиваем все клипы
            final_clip = concatenate_videoclips(processed_clips, method="compose")
            
            if progress_callback:
                progress_callback(85, "Наложение аудио...")
            
            # Накладываем аудио
            audio = AudioFileClip(self.audio_path)
            # Обрезаем аудио до длительности видео если нужно
            if audio.duration > final_clip.duration:
                audio = audio.subclip(0, final_clip.duration)
            
            final_clip = final_clip.set_audio(audio)
            
            if progress_callback:
                progress_callback(90, "Рендеринг видео...")
            
            # Рендерим видео
            final_clip.write_videofile(
                self.output_path,
                fps=self.fps,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True,
                preset='medium',
                verbose=False,
                logger=None
            )
            
            # Освобождаем ресурсы
            final_clip.close()
            audio.close()
            for clip in processed_clips:
                clip.close()
            
            if progress_callback:
                progress_callback(100, "Готово!")
            
            return True
            
        except Exception as e:
            print(f"Ошибка рендеринга: {e}")
            if progress_callback:
                progress_callback(100, f"Ошибка: {str(e)}")
            return False


class AutoEditGeneratorGUI:
    """Основной класс графического интерфейса."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AutoEdit Generator")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Переменные
        self.media_folder = tk.StringVar()
        self.audio_file = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.video_duration = tk.DoubleVar(value=30.0)
        self.beats_per_clip = tk.IntVar(value=1)
        
        # Данные
        self.media_files = []
        self.beat_times = []
        self.audio_duration = 0.0
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Настраивает пользовательский интерфейс."""
        # Основной фрейм
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Настройка grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # Выбор папки с медиа
        ttk.Label(main_frame, text="Папка с медиа:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.media_folder, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(main_frame, text="Обзор", command=self._browse_media_folder).grid(row=row, column=2, pady=5)
        row += 1
        
        # Информация о найденных файлах
        self.media_info_label = ttk.Label(main_frame, text="Файлы не выбраны")
        self.media_info_label.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=2)
        row += 1
        
        # Выбор аудиофайла
        ttk.Label(main_frame, text="Аудиофайл:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.audio_file, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(main_frame, text="Обзор", command=self._browse_audio_file).grid(row=row, column=2, pady=5)
        row += 1
        
        # Информация об аудио
        self.audio_info_label = ttk.Label(main_frame, text="Аудио не выбрано")
        self.audio_info_label.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=2)
        row += 1
        
        # Выбор папки для сохранения
        ttk.Label(main_frame, text="Папка для сохранения:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_folder, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(main_frame, text="Обзор", command=self._browse_output_folder).grid(row=row, column=2, pady=5)
        row += 1
        
        # Разделитель
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1
        
        # Параметры видео
        ttk.Label(main_frame, text="Параметры видео:").grid(row=row, column=0, sticky=tk.W, pady=5)
        row += 1
        
        # Длительность видео
        ttk.Label(main_frame, text="Длительность (сек):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(main_frame, from_=5, to=300, textvariable=self.video_duration, width=10).grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Битов на кадр
        ttk.Label(main_frame, text="Битов на кадр:").grid(row=row, column=0, sticky=tk.W, pady=5)
        beats_combo = ttk.Combobox(main_frame, textvariable=self.beats_per_clip, values=[1, 2, 4], width=10, state='readonly')
        beats_combo.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Разделитель
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1
        
        # Кнопка создания видео
        self.create_button = ttk.Button(main_frame, text="Создать видео", command=self._start_video_creation)
        self.create_button.grid(row=row, column=0, columnspan=3, pady=10)
        row += 1
        
        # Индикатор прогресса
        ttk.Label(main_frame, text="Прогресс:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.progress_bar = ttk.Progressbar(main_frame, mode='determinate', maximum=100)
        self.progress_bar.grid(row=row, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        row += 1
        
        # Лог
        ttk.Label(main_frame, text="Лог:").grid(row=row, column=0, sticky=tk.W, pady=5)
        row += 1
        
        self.log_text = tk.Text(main_frame, height=10, width=80, wrap=tk.WORD)
        self.log_text.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        main_frame.rowconfigure(row, weight=1)
        
        # Добавляем скроллбар для лога
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.grid(row=row, column=3, sticky=(tk.N, tk.S))
        self.log_text.configure(yscrollcommand=scrollbar.set)
    
    def _log(self, message: str):
        """Добавляет сообщение в лог."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def _update_progress(self, value: int, message: str = ""):
        """Обновляет индикатор прогресса."""
        self.progress_bar['value'] = value
        if message:
            self._log(message)
        self.root.update_idletasks()
    
    def _browse_media_folder(self):
        """Открывает диалог выбора папки с медиа."""
        folder = filedialog.askdirectory(title="Выберите папку с медиа")
        if folder:
            self.media_folder.set(folder)
            self._scan_media_folder(folder)
    
    def _scan_media_folder(self, folder: str):
        """Сканирует папку и подсчитывает медиафайлы."""
        supported_extensions = {'.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.mkv'}
        self.media_files = []
        
        for root, dirs, files in os.walk(folder):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in supported_extensions:
                    self.media_files.append(os.path.join(root, file))
        
        if self.media_files:
            photos = sum(1 for f in self.media_files if f.lower().endswith(('.jpg', '.jpeg', '.png')))
            videos = len(self.media_files) - photos
            self.media_info_label.config(text=f"Найдено файлов: {len(self.media_files)} (фото: {photos}, видео: {videos})")
            self._log(f"Найдено {len(self.media_files)} медиафайлов")
        else:
            self.media_info_label.config(text="Файлы не найдены!")
            self._log("В папке не найдено поддерживаемых медиафайлов")
    
    def _browse_audio_file(self):
        """Открывает диалог выбора аудиофайла."""
        file = filedialog.askopenfilename(
            title="Выберите аудиофайл",
            filetypes=[("Audio files", "*.mp3 *.wav"), ("All files", "*.*")]
        )
        if file:
            self.audio_file.set(file)
            self._analyze_audio_info(file)
    
    def _analyze_audio_info(self, audio_path: str):
        """Анализирует информацию об аудиофайле."""
        try:
            self._log("Анализ аудиофайла...")
            y, sr = librosa.load(audio_path, sr=None)
            self.audio_duration = len(y) / sr
            minutes = int(self.audio_duration // 60)
            seconds = int(self.audio_duration % 60)
            self.audio_info_label.config(text=f"Длительность: {minutes}:{seconds:02d}")
            self._log(f"Аудио загружено, длительность: {self.audio_duration:.2f} сек")
            
            # Обновляем максимальную длительность видео
            if self.video_duration.get() > self.audio_duration:
                self.video_duration.set(min(30.0, self.audio_duration))
        except Exception as e:
            self.audio_info_label.config(text="Ошибка загрузки аудио")
            self._log(f"Ошибка анализа аудио: {e}")
    
    def _browse_output_folder(self):
        """Открывает диалог выбора папки для сохранения."""
        folder = filedialog.askdirectory(title="Выберите папку для сохранения")
        if folder:
            self.output_folder.set(folder)
            self._log(f"Папка для сохранения: {folder}")
    
    def _validate_inputs(self) -> bool:
        """Проверяет корректность входных данных."""
        if not self.media_files:
            messagebox.showerror("Ошибка", "Выберите папку с медиафайлами!")
            return False
        
        if not self.audio_file.get():
            messagebox.showerror("Ошибка", "Выберите аудиофайл!")
            return False
        
        if not self.output_folder.get():
            messagebox.showerror("Ошибка", "Выберите папку для сохранения!")
            return False
        
        if self.video_duration.get() <= 0:
            messagebox.showerror("Ошибка", "Длительность видео должна быть больше 0!")
            return False
        
        return True
    
    def _start_video_creation(self):
        """Запускает процесс создания видео в отдельном потоке."""
        if not self._validate_inputs():
            return
        
        # Блокируем кнопку
        self.create_button.config(state='disabled')
        
        # Запускаем в отдельном потоке
        thread = threading.Thread(target=self._create_video, daemon=True)
        thread.start()
    
    def _create_video(self):
        """Основная функция создания видео (выполняется в отдельном потоке)."""
        try:
            # Шаг 1: Анализ битов
            self._update_progress(0, "Начало обработки...")
            
            beat_detector = BeatDetector(self.audio_file.get())
            self.beat_times, bpm, audio_duration = beat_detector.detect_beats(
                lambda val, msg: self._update_progress(val, msg)
            )
            
            self._log(f"BPM: {bpm:.1f}, найдено битов: {len(self.beat_times)}")
            
            if len(self.beat_times) < 2:
                messagebox.showwarning("Предупреждение", 
                    "Биты не обнаружены. Будет использована равномерная сетка кадров.")
            
            # Шаг 2: Построение таймлайна
            self._update_progress(10, "Построение таймлайна...")
            
            # Ограничиваем длительность видео длительностью аудио
            video_duration = min(self.video_duration.get(), audio_duration)
            
            timeline_builder = TimelineBuilder(
                self.media_files,
                self.beat_times,
                video_duration,
                self.beats_per_clip.get()
            )
            timeline = timeline_builder.build()
            
            self._log(f"Таймлайн построен: {len(timeline)} кадров")
            
            # Шаг 3: Генерация имени файла
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"edited_video_{timestamp}.mp4"
            output_path = os.path.join(self.output_folder.get(), output_filename)
            
            # Шаг 4: Рендеринг видео
            renderer = VideoRenderer(output_path, self.audio_file.get())
            success = renderer.render(
                timeline,
                lambda val, msg: self._update_progress(val, msg)
            )
            
            if success:
                self._update_progress(100, f"Видео сохранено: {output_filename}")
                messagebox.showinfo("Готово!", f"Видео успешно создано:\n{output_filename}")
            else:
                self._update_progress(100, "Ошибка при создании видео")
                messagebox.showerror("Ошибка", "Не удалось создать видео. См. лог.")
        
        except Exception as e:
            self._log(f"Критическая ошибка: {e}")
            messagebox.showerror("Ошибка", f"Произошла ошибка: {str(e)}")
        
        finally:
            # Разблокируем кнопку
            self.create_button.config(state='normal')
    
    def run(self):
        """Запускает главное окно приложения."""
        self._log("AutoEdit Generator запущен")
        self._log("Выберите папку с медиа, аудиофайл и папку для сохранения")
        self.root.mainloop()


def main():
    """Точка входа в приложение."""
    print("=" * 60)
    print("AutoEdit Generator - Создание видеороликов под музыку")
    print("=" * 60)
    
    # Проверяем зависимости
    if not check_dependencies():
        print("\nПожалуйста, установите недостающие библиотеки и запустите программу снова.")
        input("Нажмите Enter для выхода...")
        sys.exit(1)
    
    # Проверяем наличие ffmpeg
    import shutil
    if not shutil.which('ffmpeg'):
        print("\nВнимание: ffmpeg не найден в PATH!")
        print("Для работы программы необходимо установить ffmpeg:")
        print("  - Windows: скачайте с https://ffmpeg.org/download.html и добавьте в PATH")
        print("  - Linux: sudo apt-get install ffmpeg")
        print("  - macOS: brew install ffmpeg")
        print("\nПрограмма может работать некорректно без ffmpeg.\n")
    
    # Запускаем GUI
    try:
        app = AutoEditGeneratorGUI()
        app.run()
    except Exception as e:
        print(f"Ошибка запуска: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
