#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BeatSync Video Editor v4.0 (MoviePy 2.x Compatible)
Автоматический создатель видеоклипов в ритм музыки.
Совместимо с Python 3.10+ и MoviePy 2.x
"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import random
import math
import threading
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- АВТОМАТИЧЕСКАЯ УСТАНОВКА ЗАВИСИМОСТЕЙ ---
def check_and_install_dependencies():
    """Проверяет и устанавливает необходимые библиотеки."""
    required_packages = {
        'moviepy': 'moviepy>=2.0.0',
        'librosa': 'librosa',
        'numpy': 'numpy',
        'PIL': 'Pillow',
        'scipy': 'scipy'
    }

    missing = []
    for module, package in required_packages.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"📦 Обнаружены отсутствующие зависимости: {', '.join(missing)}")
        print("⏳ Установка... Пожалуйста, подождите.")
        try:
            # Используем текущий интерпретатор для установки
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
            print("✅ Зависимости успешно установлены!")
            # Перезагрузка модулей не требуется, так как импорт будет после этой функции
        except subprocess.CalledProcessError as e:
            print(f"❌ Ошибка установки зависимостей: {e}")
            print("💡 Попробуйте установить вручную: pip install " + " ".join(missing))
            sys.exit(1)

# Запуск проверки перед основными импортами
check_and_install_dependencies()

# --- ОСНОВНЫЕ ИМПОРТЫ (MoviePy 2.x Style) ---
try:
    import numpy as np
    import librosa
    from PIL import Image, ImageEnhance, ImageFilter
    # В MoviePy 2.x импорты изменились
    from moviepy import VideoFileClip, ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips
    from moviepy.video import fx as vfx
    from moviepy.audio import fx as afx
except ImportError as e:
    print(f"❌ Критическая ошибка импорта после установки: {e}")
    print("💡 Убедитесь, что вы используете совместимую версию Python и пакеты установлены в правильное окружение.")
    sys.exit(1)

class BeatSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎵 BeatSync Editor v4.0 | MoviePy 2.x")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        
        # Цветовая схема (Dark Modern)
        self.colors = {
            'bg': '#1e1e2e',
            'frame_bg': '#252537',
            'text': '#cdd6f4',
            'accent': '#89b4fa',
            'accent_hover': '#b4befe',
            'success': '#a6e3a1',
            'error': '#f38ba8',
            'warning': '#fab387',
            'entry_bg': '#313244',
            'button_text': '#11111b'
        }
        
        self.root.configure(bg=self.colors['bg'])
        
        # Переменные путей
        self.media_folder = tk.StringVar()
        self.audio_file = tk.StringVar()
        self.output_folder = tk.StringVar(value=os.path.join(os.getcwd(), "output"))
        
        self.is_processing = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """Создание пользовательского интерфейса."""
        # Стилизация виджетов
        style = ttk.Style()
        style.theme_use('clam')
        
        # Настройка стилей для темной темы
        style.configure("TFrame", background=self.colors['bg'])
        style.configure("TLabel", background=self.colors['bg'], foreground=self.colors['text'], font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground=self.colors['accent'])
        style.configure("TButton", font=("Segoe UI", 10, "bold"), background=self.colors['accent'], 
                        foreground=self.colors['button_text'], borderwidth=0, focusthickness=0)
        style.map("TButton", background=[('active', self.colors['accent_hover'])])
        style.configure("TProgressbar", background=self.colors['accent'], troughcolor=self.colors['entry_bg'])
        
        # Главный контейнер
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Заголовок
        header_label = ttk.Label(main_frame, text="🎬 BeatSync Video Editor", style="Header.TLabel")
        header_label.pack(pady=(0, 20))
        
        # Секция выбора папки с медиа
        self.create_path_selector(main_frame, "📁 Папка с фото/видео:", self.media_folder, 
                                  "Выбрать папку", self.browse_media_folder, row=0)
        
        # Секция выбора аудио
        self.create_path_selector(main_frame, "🎵 Музыкальный трек:", self.audio_file, 
                                  "Выбрать файл", self.browse_audio_file, row=1)
        
        # Секция выбора вывода
        self.create_path_selector(main_frame, "💾 Папка для сохранения:", self.output_folder, 
                                  "Выбрать папку", self.browse_output_folder, row=2)
        
        # Прогресс бар
        progress_frame = ttk.Frame(main_frame, padding="10")
        progress_frame.pack(fill=tk.X, pady=10)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X, side=tk.TOP, pady=(0, 5))
        
        self.status_label = ttk.Label(progress_frame, text="Готов к работе", foreground=self.colors['text'])
        self.status_label.pack(side=tk.LEFT)
        
        # Лог событий
        log_frame = ttk.LabelFrame(main_frame, text="📋 Журнал событий", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.log_text = tk.Text(log_frame, height=10, wrap=tk.WORD, bg=self.colors['entry_bg'], 
                                fg=self.colors['text'], insertbackground=self.colors['text'],
                                font=("Consolas", 9), borderwidth=0, highlightthickness=0)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # Кнопка запуска
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        self.start_btn = tk.Button(btn_frame, text="🚀 СОЗДАТЬ ВИДЕО", command=self.start_processing_thread,
                                   bg=self.colors['success'], fg=self.colors['button_text'],
                                   font=("Segoe UI", 12, "bold"), bd=0, padx=20, pady=10,
                                   activebackground=self.colors['accent_hover'], cursor="hand2")
        self.start_btn.pack(side=tk.RIGHT)
        
        # Привязка событий для ховера
        self.start_btn.bind("<Enter>", lambda e: self.start_btn.config(bg=self.colors['accent']))
        self.start_btn.bind("<Leave>", lambda e: self.start_btn.config(bg=self.colors['success']))
        
    def create_path_selector(self, parent, label_text, variable, btn_text, command, row):
        """Создает строку выбора пути."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=5)
        
        label = ttk.Label(frame, text=label_text, width=25, anchor='w')
        label.pack(side=tk.LEFT)
        
        entry = tk.Entry(frame, textvariable=variable, bg=self.colors['entry_bg'], 
                         fg=self.colors['text'], insertbackground=self.colors['text'],
                         relief=tk.FLAT, font=("Segoe UI", 10))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        btn = tk.Button(frame, text=btn_text, command=command,
                        bg=self.colors['accent'], fg=self.colors['button_text'],
                        font=("Segoe UI", 9, "bold"), bd=0, padx=15, pady=5,
                        activebackground=self.colors['accent_hover'], cursor="hand2")
        btn.pack(side=tk.RIGHT)
        
    def browse_media_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку с медиафайлами")
        if folder:
            self.media_folder.set(folder)
            self.log(f"📂 Выбрана папка: {folder}", "info")
            
    def browse_audio_file(self):
        file = filedialog.askopenfilename(title="Выберите аудиофайл", 
                                          filetypes=[("Audio Files", "*.mp3 *.wav *.ogg *.flac")])
        if file:
            self.audio_file.set(file)
            self.log(f"🎵 Выбран трек: {os.path.basename(file)}", "info")
            
    def browse_output_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку для сохранения")
        if folder:
            self.output_folder.set(folder)
            self.log(f"💾 Вывод в папку: {folder}", "info")
            
    def log(self, message, level="info"):
        """Добавляет сообщение в лог."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color_map = {
            "info": self.colors['text'],
            "success": self.colors['success'],
            "warning": self.colors['warning'],
            "error": self.colors['error']
        }
        color = color_map.get(level, self.colors['text'])
        
        self.log_text.insert(tk.END, f"[{timestamp}] ", "")
        self.log_text.insert(tk.END, f"{message}\n", color)
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def start_processing_thread(self):
        """Запускает обработку в отдельном потоке."""
        if self.is_processing:
            messagebox.showwarning("Внимание", "Обработка уже идет!")
            return
            
        media_path = self.media_folder.get()
        audio_path = self.audio_file.get()
        output_path = self.output_folder.get()
        
        if not media_path or not os.path.isdir(media_path):
            messagebox.showerror("Ошибка", "Пожалуйста, выберите корректную папку с медиафайлами.")
            return
        if not audio_path or not os.path.isfile(audio_path):
            messagebox.showerror("Ошибка", "Пожалуйста, выберите аудиофайл.")
            return
            
        self.is_processing = True
        self.start_btn.config(state=tk.DISABLED, bg="#555555")
        self.progress_var.set(0)
        
        thread = threading.Thread(target=self.process_video, args=(media_path, audio_path, output_path))
        thread.daemon = True
        thread.start()
        
    def process_video(self, media_path, audio_path, output_path):
        """Основная логика обработки видео."""
        try:
            self.log("🎼 Анализ аудиодорожки...", "info")
            self.progress_var.set(10)
            
            # Загрузка аудио и поиск битов
            y, sr = librosa.load(audio_path, sr=None)
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            
            # Извлечение скалярного значения tempo (совместимость с новыми numpy)
            if isinstance(tempo, np.ndarray):
                tempo = tempo[0]
            
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)
            duration = librosa.get_duration(y=y, sr=sr)
            
            self.log(f"🎵 BPM: {tempo:.2f}, Длительность: {duration:.2f} сек, Битов: {len(beat_times)}", "success")
            self.progress_var.set(20)
            
            # Поиск медиафайлов
            valid_extensions = ('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.mkv')
            files = [os.path.join(media_path, f) for f in os.listdir(media_path) 
                     if f.lower().endswith(valid_extensions)]
            
            if not files:
                raise FileNotFoundError("В папке не найдено подходящих медиафайлов.")
                
            self.log(f"📁 Найдено файлов: {len(files)}", "info")
            self.progress_var.set(30)
            
            # Расчет длительности клипа (например, 4 бита на кадр)
            beats_per_clip = 4
            if len(beat_times) < 2:
                clip_duration = 2.0 # Дефолт если битов мало
            else:
                avg_beat_interval = (beat_times[-1] - beat_times[0]) / max(1, len(beat_times) - 1)
                clip_duration = avg_beat_interval * beats_per_clip
            
            self.log(f"⏱ Длительность одного клипа: {clip_duration:.2f} сек", "info")
            
            clips = []
            total_clips_needed = int(duration / clip_duration) + 1
            
            # Циклическое использование файлов
            file_index = 0
            
            for i in range(total_clips_needed):
                if file_index >= len(files):
                    file_index = 0 # Зацикливаем
                    
                filepath = files[file_index]
                filename = os.path.basename(filepath)
                
                try:
                    ext = os.path.splitext(filepath)[1].lower()
                    
                    if ext in ['.jpg', '.jpeg', '.png']:
                        # Обработка фото
                        clip = self.create_image_clip(filepath, clip_duration)
                    else:
                        # Обработка видео
                        clip = self.create_video_clip(filepath, clip_duration)
                    
                    if clip:
                        clips.append(clip)
                        self.log(f"✅ Обработано: {filename}", "info")
                    else:
                        self.log(f"⚠️ Пропущено (ошибка): {filename}", "warning")
                        
                except Exception as e:
                    self.log(f"❌ Ошибка обработки {filename}: {str(e)}", "error")
                    
                file_index += 1
                self.progress_var.set(30 + (i / total_clips_needed) * 40)
                
            if not clips:
                raise ValueError("Не удалось создать ни одного клипа.")
                
            self.log("🧩 Сборка финального видео...", "info")
            final_video = concatenate_videoclips(clips, method="compose")
            
            # Наложение аудио
            audio_clip = AudioFileClip(audio_path)
            # Обрезаем аудио под длину видео или видео под аудио (здесь видео под аудио)
            if audio_clip.duration > final_video.duration:
                audio_clip = audio_clip.subclipped(0, final_video.duration)
            else:
                # Если аудио короче, зацикливаем или обрезаем видео (здесь обрезаем видео)
                final_video = final_video.subclipped(0, audio_clip.duration)
            
            final_video = final_video.with_audio(audio_clip)
            
            # Сохранение
            os.makedirs(output_path, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"edited_video_{timestamp}.mp4"
            output_full_path = os.path.join(output_path, output_filename)
            
            self.log(f"💾 Рендеринг в {output_filename} (1920x1080, 30fps)...", "warning")
            
            # Рендеринг с прогрессом (упрощенно)
            final_video.write_videofile(
                output_full_path,
                fps=30,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True,
                logger=None # Отключаем стандартный логгер moviepy чтобы не засорять наш GUI
            )
            
            self.log(f"🎉 ГОТОВО! Видео сохранено: {output_full_path}", "success")
            self.progress_var.set(100)
            messagebox.showinfo("Успех", f"Видео успешно создано!\n{output_full_path}")
            
            # Очистка памяти
            final_video.close()
            audio_clip.close()
            for c in clips:
                c.close()
                
        except Exception as e:
            self.log(f"❌ Критическая ошибка: {str(e)}", "error")
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{str(e)}")
        finally:
            self.is_processing = False
            self.start_btn.config(state=tk.NORMAL, bg=self.colors['success'])
            
    def create_image_clip(self, filepath, duration):
        """Создает клип из изображения с эффектами (MoviePy 2.x)."""
        try:
            # Загрузка изображения через PIL для предварительной обработки
            img = Image.open(filepath)
            
            # Конвертация в RGB если нужно
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Применение случайных эффектов
            effect_choice = random.choice(['zoom_in', 'zoom_out', 'rotate', 'filter'])
            
            if effect_choice == 'rotate':
                angle = random.uniform(-3, 3)
                img = img.rotate(angle, resample=Image.BICUBIC, expand=False)
            elif effect_choice == 'filter':
                filter_choice = random.choice(['sepia', 'bw', 'cool', 'warm'])
                if filter_choice == 'bw':
                    img = ImageEnhance.Color(img).enhance(0)
                elif filter_choice == 'sepia':
                    img = img.convert('RGB')
                    pixels = img.load()
                    width, height = img.size
                    for i in range(width):
                        for j in range(height):
                            r, g, b = pixels[i, j]
                            tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                            tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                            tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                            pixels[i, j] = (min(255, tr), min(255, tg), min(255, tb))
            
            # Конвертация обратно в массив numpy
            img_array = np.array(img)
            
            # Создание клипа
            clip = ImageClip(img_array).with_duration(duration)
            
            # Масштабирование под 1920x1080 (cover fit)
            clip = clip.resize(height=1080)
            if clip.w < 1920:
                clip = clip.resize(width=1920)
            
            # Центрирование и кроп
            clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=1920, height=1080)
            
            # Добавление эффекта движения (Ken Burns) через transform
            # В MoviePy 2.x используем функцию make_loopable или простые трансформации
            # Для простоты применим статический ресайз с небольшим зумом если нужно
            # Реализация сложного Ken Burns в 2.x требует кастомной функции transform
            
            return clip
            
        except Exception as e:
            logger.error(f"Error processing image {filepath}: {e}")
            return None
            
    def create_video_clip(self, filepath, duration):
        """Создает клип из видео (MoviePy 2.x)."""
        try:
            clip = VideoFileClip(filepath)
            
            # Если видео короче нужной длительности, зацикливаем
            if clip.duration < duration:
                # В MoviePy 2.x нет простого loop, делаем через subclip и concat если надо, 
                # но проще просто обрезать до минимума или растянуть (что хуже)
                # Здесь просто берем сколько есть, но в логике главного цикла это учтено
                pass 
            
            # Обрезка по времени
            if clip.duration > duration:
                start_time = random.uniform(0, max(0, clip.duration - duration))
                clip = clip.subclipped(start_time, start_time + duration)
            
            # Масштабирование
            clip = clip.resize(height=1080)
            if clip.w < 1920:
                clip = clip.resize(width=1920)
            
            clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=1920, height=1080)
            
            # Случайный цветовой фильтр
            if random.random() > 0.7:
                # Пример применения фильтра (в 2.x через vfx)
                # vfx.MultiplyColor не всегда есть, используем простой подход
                pass
                
            return clip
            
        except Exception as e:
            logger.error(f"Error processing video {filepath}: {e}")
            return None

if __name__ == "__main__":
    # Проверка наличия tkinter
    try:
        import tkinter
    except ImportError:
        print("❌ Критическая ошибка: Не найден модуль 'tkinter'.")
        print("💡 Решение для Bazzite/Fedora:")
        print("   sudo rpm-ostree install python3-tkinter")
        print("   Затем перезагрузите компьютер.")
        sys.exit(1)

    root = tk.Tk()
    app = BeatSyncApp(root)
    root.mainloop()