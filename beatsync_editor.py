#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BeatSync Video Editor v4.1 (MoviePy 2.x Compatible)
Автоматический генератор видеоклипов в ритм музыки.
Исправлена совместимость с MoviePy 2.x (эффекты, импорты).
"""

import os
import sys
import subprocess
import datetime
import random
import logging
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Автоматическая установка зависимостей ---
def install_dependencies():
    """Проверяет и устанавливает необходимые зависимости."""
    required_packages = [
        'moviepy', 'librosa', 'numpy', 'Pillow', 'scipy', 'audioread'
    ]
    missing = []
    
    for package in required_packages:
        try:
            if package == 'Pillow':
                __import__('PIL')
            elif package == 'moviepy':
                __import__('moviepy')
            else:
                __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        print("📦 Установка отсутствующих зависимостей...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("✅ Зависимости установлены успешно.")
        except subprocess.CalledProcessError:
            print("❌ Ошибка установки зависимостей. Установите их вручную:")
            print(f"   {sys.executable} -m pip install {' '.join(missing)}")
            sys.exit(1)

# Запуск установки перед импортом тяжелых библиотек
install_dependencies()

# Импорты после установки
import librosa
# В MoviePy 2.x импорты изменились. Эффекты теперь в moviepy.video.fx и moviepy.audio.fx
from moviepy import (
    VideoFileClip, ImageClip, AudioFileClip, 
    CompositeVideoClip, concatenate_videoclips
)
# Исправленный импорт эффектов для v2.x
from moviepy.video.fx import Resize, Rotate, BlackAndWhite, MirrorX, MirrorY, MultiplyColor
from moviepy.audio.fx import AudioFadeIn, AudioFadeOut

# Константы
TARGET_RESOLUTION = (1920, 1080)
FPS = 30
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}

class BeatSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎵 BeatSync Video Editor v4.1")
        self.root.geometry("800x600")
        self.root.resizable(False, False)
        
        # Переменные путей
        self.media_folder = tk.StringVar()
        self.audio_file = tk.StringVar()
        self.output_folder = tk.StringVar(value=os.getcwd())
        
        self.setup_ui()
        
    def setup_ui(self):
        """Создание графического интерфейса."""
        # Стиль
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', font=('Arial', 11), padding=10)
        style.configure('TLabel', font=('Arial', 11))
        style.configure('Header.TLabel', font=('Arial', 16, 'bold'))
        
        # Основной фрейм
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Заголовок
        title_label = ttk.Label(main_frame, text="🎬 BeatSync Video Editor", style='Header.TLabel')
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Выбор папки с медиа
        ttk.Label(main_frame, text="📁 Папка с фото/видео:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.media_folder, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(main_frame, text="Обзор...", command=self.browse_media).grid(row=1, column=2)
        
        # Выбор аудио
        ttk.Label(main_frame, text="🎵 Музыкальный файл:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.audio_file, width=50).grid(row=2, column=1, padx=5)
        ttk.Button(main_frame, text="Обзор...", command=self.browse_audio).grid(row=2, column=2)
        
        # Выбор папки вывода
        ttk.Label(main_frame, text="📂 Папка для сохранения:").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_folder, width=50).grid(row=3, column=1, padx=5)
        ttk.Button(main_frame, text="Обзор...", command=self.browse_output).grid(row=3, column=2)
        
        # Прогресс бар
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=20)
        
        # Статус
        self.status_label = ttk.Label(main_frame, text="Готов к работе", anchor=tk.CENTER)
        self.status_label.grid(row=5, column=0, columnspan=3, pady=5)
        
        # Кнопка создания
        self.create_button = ttk.Button(main_frame, text="✨ Создать видео", command=self.start_creation)
        self.create_button.grid(row=6, column=0, columnspan=3, pady=20)
        
    def browse_media(self):
        folder = filedialog.askdirectory(title="Выберите папку с медиафайлами")
        if folder:
            self.media_folder.set(folder)
            
    def browse_audio(self):
        file = filedialog.askopenfilename(
            title="Выберите аудиофайл",
            filetypes=[("Audio files", "*.mp3 *.wav *.ogg *.flac")]
        )
        if file:
            self.audio_file.set(file)
            
    def browse_output(self):
        folder = filedialog.askdirectory(title="Выберите папку для сохранения")
        if folder:
            self.output_folder.set(folder)
            
    def update_status(self, message):
        self.status_label.config(text=message)
        self.root.update_idletasks()
        
    def update_progress(self, value):
        self.progress_var.set(value)
        self.root.update_idletasks()
        
    def start_creation(self):
        media_path = self.media_folder.get()
        audio_path = self.audio_file.get()
        output_path = self.output_folder.get()
        
        if not media_path or not os.path.isdir(media_path):
            messagebox.showerror("Ошибка", "Выберите корректную папку с медиафайлами!")
            return
        if not audio_path or not os.path.isfile(audio_path):
            messagebox.showerror("Ошибка", "Выберите аудиофайл!")
            return
            
        self.create_button.config(state='disabled')
        try:
            self.process_video(media_path, audio_path, output_path)
            messagebox.showinfo("Успех", f"Видео создано!\nПапка: {output_path}")
        except Exception as e:
            logger.exception("Критическая ошибка")
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{str(e)}")
        finally:
            self.create_button.config(state='normal')
            
    def process_video(self, media_path, audio_path, output_path):
        """Основной процесс создания видео."""
        self.update_status("⏳ Анализ аудио и поиск битов...")
        
        # Анализ аудио
        try:
            y, sr = librosa.load(audio_path, sr=None)
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)
            
            if len(beat_times) == 0:
                raise ValueError("Не удалось обнаружить биты в аудиофайле.")
                
            bpm = float(tempo)
            beat_interval = 60.0 / bpm
            clip_duration = beat_interval * 4  # 4 бита на такт
            
            logger.info(f"BPM: {bpm:.2f}, Интервал: {beat_interval:.2f}s, Длительность клипа: {clip_duration:.2f}s")
        except Exception as e:
            logger.error(f"Ошибка анализа аудио: {e}")
            raise
            
        self.update_status("📂 Загрузка медиафайлов...")
        
        # Сбор файлов
        files = []
        for f in os.listdir(media_path):
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                files.append(os.path.join(media_path, f))
                
        if not files:
            raise ValueError("В папке не найдено поддерживаемых изображений или видео.")
            
        logger.info(f"Найдено файлов: {len(files)}")
        
        # Загрузка аудио
        self.update_status("🎵 Загрузка аудиодорожки...")
        audio_clip = AudioFileClip(audio_path)
        total_duration = audio_clip.duration
        
        # Создание клипов
        self.update_status("🎬 Обработка кадров...")
        clips = []
        num_beats = int(total_duration / beat_interval)
        
        # Функции эффектов для MoviePy 2.x
        def apply_random_image_effect(clip):
            effect_choice = random.choice(['zoom', 'rotate', 'color'])
            
            if effect_choice == 'zoom':
                factor = random.uniform(1.1, 1.3)
                return clip.fx(Resize, size=factor)
            elif effect_choice == 'rotate':
                angle = random.uniform(-3, 3)
                return clip.fx(Rotate, angle)
            else:
                # Цветовой эффект
                filter_type = random.choice(['sepia', 'bw', 'cool'])
                if filter_type == 'bw':
                    return clip.fx(BlackAndWhite)
                elif filter_type == 'cool':
                    # Холодный оттенок через умножение цвета (R, G, B)
                    return clip.fx(MultiplyColor, (0.8, 0.9, 1.2))
                else:
                    # Теплый/Сепия
                    return clip.fx(MultiplyColor, (1.2, 1.0, 0.7))
                    
            return clip

        def apply_random_video_effect(clip):
            return apply_random_image_effect(clip)

        current_time = 0
        file_index = 0
        
        progress_step = 100 / num_beats if num_beats > 0 else 1
        
        while current_time < total_duration - beat_interval:
            self.update_progress(min(100, (current_time / total_duration) * 100))
            
            # Выбор файла (циклично)
            if not files: break
            file_path = files[file_index % len(files)]
            ext = os.path.splitext(file_path)[1].lower()
            
            try:
                if ext in IMAGE_EXTENSIONS:
                    # Создание клипа из изображения
                    img_clip = ImageClip(file_path).with_duration(clip_duration) 
                    # Ресайз под разрешение (cover mode эмуляция)
                    img_clip = img_clip.fx(Resize, width=TARGET_RESOLUTION[0])
                    if img_clip.h < TARGET_RESOLUTION[1]:
                         img_clip = img_clip.fx(Resize, height=TARGET_RESOLUTION[1])
                    
                    # Центрирование (crop)
                    w, h = img_clip.size
                    x_center = w // 2
                    y_center = h // 2
                    x1 = max(0, x_center - TARGET_RESOLUTION[0]//2)
                    y1 = max(0, y_center - TARGET_RESOLUTION[1]//2)
                    
                    img_clip = img_clip.crop(x1=x1, y1=y1, width=TARGET_RESOLUTION[0], height=TARGET_RESOLUTION[1])
                    
                    # Применение эффектов
                    img_clip = apply_random_image_effect(img_clip)
                    clips.append(img_clip)
                    
                elif ext in VIDEO_EXTENSIONS:
                    vid_clip = VideoFileClip(file_path)
                    
                    # Если видео короче нужной длительности, зацикливаем
                    if vid_clip.duration < clip_duration:
                        repeats = int(clip_duration / vid_clip.duration) + 1
                        subclips = [vid_clip] * repeats
                        vid_clip = concatenate_videoclips(subclips)
                    
                    vid_clip = vid_clip.subclipped(0, clip_duration)
                    
                    # Ресайз и кроп
                    vid_clip = vid_clip.fx(Resize, width=TARGET_RESOLUTION[0])
                    if vid_clip.h < TARGET_RESOLUTION[1]:
                        vid_clip = vid_clip.fx(Resize, height=TARGET_RESOLUTION[1])
                        
                    w, h = vid_clip.size
                    x_center = w // 2
                    y_center = h // 2
                    x1 = max(0, x_center - TARGET_RESOLUTION[0]//2)
                    y1 = max(0, y_center - TARGET_RESOLUTION[1]//2)
                    
                    vid_clip = vid_clip.crop(x1=x1, y1=y1, width=TARGET_RESOLUTION[0], height=TARGET_RESOLUTION[1])
                    
                    # Эффекты
                    vid_clip = apply_random_video_effect(vid_clip)
                    clips.append(vid_clip)
                    
                else:
                    pass
                    
                file_index += 1
                current_time += clip_duration
                
            except Exception as e:
                logger.error(f"Ошибка обработки файла {file_path}: {e}")
                file_index += 1
                continue

        if not clips:
            raise ValueError("Не удалось создать ни одного клипа.")
            
        # Сборка финального видео
        self.update_status("🚀 Сборка финального видео...")
        final_clip = concatenate_videoclips(clips, method="compose")
        
        # Обрезка под длину аудио
        if final_clip.duration > audio_clip.duration:
            final_clip = final_clip.subclipped(0, audio_clip.duration)
            
        final_clip = final_clip.with_audio(audio_clip)
        
        # Формирование имени файла
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"edited_video_{timestamp}.mp4"
        output_full_path = os.path.join(output_path, output_filename)
        
        # Экспорт
        logger.info(f"Рендеринг видео в {output_full_path}...")
        final_clip.write_videofile(
            output_full_path,
            fps=FPS,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            preset='medium',
            threads=4
        )
        
        # Очистка
        final_clip.close()
        audio_clip.close()
        for c in clips:
            c.close()
            
        self.update_progress(100)
        self.update_status("✅ Готово!")
        logger.info(f"Видео успешно создано: {output_full_path}")

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = BeatSyncApp(root)
        root.mainloop()
    except Exception as e:
        logger.critical(f"Запуск приложения не удался: {e}")
        # Проверка на наличие tkinter в системе
        if "tkinter" in str(e):
            print("\n❌ Критическая ошибка: Не найден модуль 'tkinter'.")
            print("💡 Решение для Bazzite/Fedora:")
            print("   sudo rpm-ostree install python3-tkinter")
            print("   После установки перезагрузите компьютер.")
        else:
            print(f"❌ Ошибка: {e}")
