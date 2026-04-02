from flask import Flask, render_template, request, jsonify, send_file, url_for
import os
import threading
import time
import glob
import shutil
from datetime import datetime
import numpy as np

# Проверка и импорт библиотек для обработки видео
try:
    import librosa
    from moviepy.editor import (VideoFileClip, ImageClip, concatenate_videoclips, 
                                AudioFileClip, CompositeVideoClip)
    from moviepy import vfx
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Установите зависимости: pip install -r requirements.txt")
    exit(1)

app = Flask(__name__)

# Конфигурация
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
ALLOWED_EXTENSIONS_MEDIA = {'jpg', 'jpeg', 'png', 'mp4', 'mov', 'avi', 'mkv'}
ALLOWED_EXTENSIONS_AUDIO = {'mp3', 'wav'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB лимит

# Создание папок
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Глобальная переменная для статуса прогресса
progress_status = {"percent": 0, "message": "Ожидание...", "active": False}

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def detect_beats(audio_path, sr=None):
    """Анализ аудио и детекция битов"""
    try:
        y, sr = librosa.load(audio_path, sr=sr)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        
        if len(beat_times) == 0:
            return None, None, "Биты не обнаружены. Используется равномерная сетка."
        
        return float(tempo), beat_times.tolist(), None
    except Exception as e:
        return None, None, str(e)

def apply_ken_burns_effect(clip, duration):
    """Применение эффекта Кен Бёрнс (масштабирование и панорамирование)"""
    import random
    
    # Случайное направление и масштаб
    zoom_start = 1.0
    zoom_end = 1.0 + random.uniform(0.05, 0.15)
    
    # Генерация случайных координат для панорамирования
    w, h = clip.size
    max_shift_x = int(w * 0.1)
    max_shift_y = int(h * 0.1)
    
    start_x = random.randint(-max_shift_x, max_shift_x)
    start_y = random.randint(-max_shift_y, max_shift_y)
    end_x = random.randint(-max_shift_x, max_shift_x)
    end_y = random.randint(-max_shift_y, max_shift_y)
    
    def transform(get_frame, t):
        frame = get_frame(t)
        progress = t / duration if duration > 0 else 0
        
        # Интерполяция позиции и зума
        current_zoom = zoom_start + (zoom_end - zoom_start) * progress
        current_x = int(start_x + (end_x - start_x) * progress)
        current_y = int(start_y + (end_y - start_y) * progress)
        
        # Применение трансформации (упрощённо через crop и resize)
        # В реальной реализации лучше использовать affine_transform
        return frame
    
    # Применяем эффект скорости для симуляции движения (упрощённая версия)
    # Для полноценного Кен Бёрнс требуется более сложная логика с PIL/Pillow
    return clip.resize(lambda t: 1 + 0.1 * (t / duration))

def apply_color_filter(clip):
    """Случайный цветовой фильтр"""
    import random
    filters = [
        lambda c: c.fx(vfx.colorx, 1.2),  # Тёплый
        lambda c: c.fx(vfx.colorx, 0.8),  # Холодный
        lambda c: c.fx(vfx.lum_contrast, contrast=1.2),  # Контраст
        lambda c: c  # Без изменений
    ]
    selected = random.choice(filters)
    return selected(clip)

def process_clip(media_path, duration, is_video=False):
    """Обработка одного медиафайла (фото или видео)"""
    try:
        if is_video:
            clip = VideoFileClip(media_path)
            # Обрезка или зацикливание до нужной длительности
            if clip.duration < duration:
                # Зацикливание или замедление
                clip = clip.loop(duration=duration)
            else:
                clip = clip.subclip(0, duration)
            
            # Случайное ускорение/замедление
            speed = np.random.uniform(0.8, 1.2)
            clip = clip.speedx(speed)
            if clip.duration > duration:
                clip = clip.subclip(0, duration)
                
        else:
            # Фотография
            clip = ImageClip(media_path).set_duration(duration)
            # Эффект Кен Бёрнс
            clip = apply_ken_burns_effect(clip, duration)
        
        # Цветовой фильтр
        clip = apply_color_filter(clip)
        
        # Ресайз до 1920x1080
        clip = clip.resize((1920, 1080))
        
        return clip
    except Exception as e:
        print(f"Ошибка обработки {media_path}: {e}")
        return None

def add_transition(clip, duration=0.2):
    """Добавление перехода (fade in/out)"""
    return clip.fadein(duration).fadeout(duration)

def build_timeline(media_files, audio_path, duration_limit, beats_per_frame):
    """Построение таймлайна на основе битов или равномерной сетки"""
    global progress_status
    
    progress_status["message"] = "Анализ битов..."
    tempo, beat_times, error = detect_beats(audio_path)
    
    if error or not beat_times:
        progress_status["message"] = "Биты не найдены, используется равномерная сетка."
        # Равномерная сетка каждые 2 секунды
        total_frames = int(duration_limit / 2)
        frame_durations = [2.0] * total_frames
        if frame_durations:
            frame_durations[-1] = duration_limit - sum(frame_durations[:-1])
        return frame_durations, "Равномерная сетка (биты не обнаружены)"
    
    progress_status["message"] = f"Найдено битов: {len(beat_times)}. Темп: {tempo:.1f} BPM"
    
    # Ограничиваем длительность аудио
    audio_clip = AudioFileClip(audio_path)
    audio_duration = audio_clip.duration
    audio_clip.close()
    
    effective_duration = min(duration_limit, audio_duration)
    
    # Распределение битов по кадрам
    # Берём биты только в пределах эффективной длительности
    valid_beats = [b for b in beat_times if b < effective_duration]
    
    if len(valid_beats) < 2:
        # Если битов мало, используем равномерную сетку
        total_frames = max(1, int(effective_duration / 2))
        frame_durations = [effective_duration / total_frames] * total_frames
        return frame_durations, "Мало битов, используется равномерная сетка"
    
    # Группируем биты по beats_per_frame
    frame_durations = []
    total_time = 0
    
    i = 0
    while i < len(valid_beats) and total_time < effective_duration:
        # Начало текущего кадра
        start_time = valid_beats[i]
        
        # Конец кадра через N битов
        end_idx = min(i + beats_per_frame, len(valid_beats))
        if end_idx <= i:
            break
            
        end_time = valid_beats[end_idx - 1]
        
        # Длительность кадра
        frame_dur = end_time - start_time
        if frame_dur > 0:
            frame_durations.append(frame_dur)
            total_time += frame_dur
        
        i = end_idx
    
    # Если остались незаполненные секунды, добавляем последний кадр
    if total_time < effective_duration and len(valid_beats) > 0:
        remaining = effective_duration - total_time
        if remaining > 0.5:
            frame_durations.append(remaining)
    
    if not frame_durations:
        # Фолбэк
        frame_durations = [2.0] * max(1, int(effective_duration / 2))
    
    return frame_durations, f"Таймлайн построен по битам ({len(frame_durations)} кадров)"

def generate_video(media_folder, audio_path, output_path, duration_limit, beats_per_frame, update_progress):
    """Основная функция генерации видео"""
    global progress_status
    
    try:
        # Сбор медиафайлов
        media_files = []
        for ext in ALLOWED_EXTENSIONS_MEDIA:
            media_files.extend(glob.glob(os.path.join(media_folder, f"*.{ext}")))
            media_files.extend(glob.glob(os.path.join(media_folder, f"*.{ext.upper()}")))
        
        if not media_files:
            raise ValueError("Медиафайлы не найдены в указанной папке")
        
        # Построение таймлайна
        frame_durations, timeline_msg = build_timeline(
            media_files, audio_path, duration_limit, beats_per_frame
        )
        update_progress(10, f"Таймлайн: {timeline_msg}")
        
        if not frame_durations:
            raise ValueError("Не удалось построить таймлайн")
        
        # Обработка клипов
        processed_clips = []
        total_frames = len(frame_durations)
        
        for i, duration in enumerate(frame_durations):
            # Циклический выбор файла
            file_idx = i % len(media_files)
            file_path = media_files[file_idx]
            is_video = file_path.lower().endswith(('mp4', 'mov', 'avi', 'mkv'))
            
            update_progress(20 + int(60 * i / total_frames), f"Обработка кадра {i+1}/{total_frames}")
            
            clip = process_clip(file_path, duration, is_video)
            if clip:
                # Добавляем переход (кроме последнего)
                if i < total_frames - 1:
                    clip = add_transition(clip, 0.2)
                processed_clips.append(clip)
        
        if not processed_clips:
            raise ValueError("Не удалось обработать ни одного файла")
        
        # Конкатенация
        update_progress(85, "Сборка видео...")
        final_video = concatenate_videoclips(processed_clips, method="compose")
        
        # Наложение аудио
        audio = AudioFileClip(audio_path)
        if final_video.duration > audio.duration:
            audio = audio.loop(duration=final_video.duration)
        else:
            audio = audio.subclip(0, final_video.duration)
        
        final_video = final_video.set_audio(audio)
        
        # Рендеринг
        update_progress(90, "Рендеринг финального видео...")
        final_video.write_videofile(
            output_path,
            fps=30,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            preset='medium',
            threads=4
        )
        
        # Очистка
        for clip in processed_clips:
            clip.close()
        final_video.close()
        audio.close()
        
        update_progress(100, "Готово!")
        return True
        
    except Exception as e:
        update_progress(0, f"Ошибка: {str(e)}")
        print(f"Error in generate_video: {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    global progress_status
    
    if 'media' not in request.files and 'audio' not in request.files:
        return jsonify({"error": "Нет файлов"}), 400
    
    # Очистка папок
    for folder in [UPLOAD_FOLDER]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder, exist_ok=True)
    
    media_count = 0
    audio_path = None
    
    # Загрузка медиа
    if 'media' in request.files:
        files = request.files.getlist('media')
        for file in files:
            if file.filename and allowed_file(file.filename, ALLOWED_EXTENSIONS_MEDIA):
                filepath = os.path.join(UPLOAD_FOLDER, file.filename)
                file.save(filepath)
                media_count += 1
    
    # Загрузка аудио
    if 'audio' in request.files:
        file = request.files['audio']
        if file.filename and allowed_file(file.filename, ALLOWED_EXTENSIONS_AUDIO):
            audio_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(audio_path)
    
    if media_count == 0:
        return jsonify({"error": "Медиафайлы не загружены"}), 400
    if not audio_path:
        return jsonify({"error": "Аудиофайл не загружен"}), 400
    
    # Параметры
    try:
        duration_limit = float(request.form.get('duration', 30))
        beats_per_frame = int(request.form.get('beats', 1))
    except ValueError:
        return jsonify({"error": "Неверные параметры"}), 400
    
    # Запуск генерации в потоке
    output_filename = f"edited_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    
    def run_generation():
        global progress_status
        progress_status = {"percent": 0, "message": "Запуск...", "active": True}
        
        def update_progress(percent, message):
            progress_status["percent"] = percent
            progress_status["message"] = message
        
        success = generate_video(
            UPLOAD_FOLDER, 
            audio_path, 
            output_path, 
            duration_limit, 
            beats_per_frame,
            update_progress
        )
        
        progress_status["active"] = False
        progress_status["success"] = success
        if success:
            progress_status["output_file"] = output_filename
    
    thread = threading.Thread(target=run_generation)
    thread.start()
    
    return jsonify({"status": "started", "message": f"Загружено {media_count} файлов. Генерация началась."})

@app.route('/progress')
def get_progress():
    return jsonify(progress_status)

@app.route('/download/<filename>')
def download_file(filename):
    filepath = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({"error": "Файл не найден"}), 404

@app.route('/video/<filename>')
def stream_video(filename):
    filepath = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath)
    return jsonify({"error": "Файл не найден"}), 404

if __name__ == '__main__':
    print("Запуск сервера... Откройте http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
