import os
import asyncio
import time
import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime
import tkinter as tk
from tkinter import filedialog
import threading
import urllib.request
import zipfile
import shutil
import sys

from fastapi import FastAPI, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import yt_dlp
import aiofiles

app = FastAPI(title="YouTube 视频下载工具")

# 确保所有必要的目录存在
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)

# 确保视频目录存在
VIDEOS_DIR = Path("videos")
VIDEOS_DIR.mkdir(exist_ok=True)

# 确保模板目录存在
TEMPLATES_DIR = Path("templates")
TEMPLATES_DIR.mkdir(exist_ok=True)

# 配置静态文件和模板
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 存储下载任务的状态
downloads = {}

class DownloadLogger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(f"Error: {msg}")

class Video:
    def __init__(self, video_id, title, author, duration, description, filepath, size, thumbnail=None):
        self.video_id = video_id
        self.title = title
        self.author = author
        self.duration = duration
        self.description = description
        self.filepath = filepath
        self.size = size
        self.thumbnail = thumbnail
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self):
        return {
            "video_id": self.video_id,
            "title": self.title,
            "author": self.author,
            "duration": self.duration,
            "description": self.description,
            "filepath": str(self.filepath),
            "size": self.size,
            "thumbnail": self.thumbnail,
            "created_at": self.created_at
        }

def load_videos():
    """加载已下载的视频列表"""
    data_file = Path("videos/videos.json")
    if data_file.exists():
        with open(data_file, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_videos(videos):
    """保存视频列表到JSON文件"""
    data_file = Path("videos/videos.json")
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)

def format_duration(seconds):
    """将秒转换为时分秒格式"""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}"
    else:
        return f"{int(minutes):02d}:{int(seconds):02d}"

def format_size(bytes):
    """将字节转换为可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} TB"

def setup_ffmpeg():
    """设置 FFmpeg 环境"""
    ffmpeg_dir = Path("ffmpeg")
    if not ffmpeg_dir.exists():
        print("正在下载 FFmpeg...")
        # 下载 FFmpeg
        ffmpeg_url = "https://github.com/GyanD/codexffmpeg/releases/download/6.1.1/ffmpeg-6.1.1-full_build.zip"
        zip_path = "ffmpeg.zip"
        
        try:
            # 下载文件
            urllib.request.urlretrieve(ffmpeg_url, zip_path)
            
            # 解压文件
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(".")
            
            # 重命名文件夹
            extracted_dir = next(Path(".").glob("ffmpeg-*"))
            shutil.move(str(extracted_dir), str(ffmpeg_dir))
            
            # 清理下载的 zip 文件
            os.remove(zip_path)
            
            # 将 FFmpeg 添加到环境变量
            ffmpeg_bin = str(ffmpeg_dir / "bin")
            if ffmpeg_bin not in os.environ["PATH"]:
                os.environ["PATH"] = ffmpeg_bin + os.pathsep + os.environ["PATH"]
                
            print("FFmpeg 设置完成！")
        except Exception as e:
            print(f"设置 FFmpeg 时出错: {e}")
            return False
    return str(ffmpeg_dir / "bin" / "ffmpeg.exe")

async def download_video(video_url, download_id, download_dir=None, format_type="video"):
    """异步下载视频"""
    downloads[download_id] = {"status": "downloading", "progress": 0}
    
    # 获取 FFmpeg 路径
    ffmpeg_path = setup_ffmpeg()
    if not ffmpeg_path:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = "FFmpeg 设置失败"
        return
    
    def progress_hook(d):
        if d['status'] == 'downloading':
            if 'total_bytes' in d and d['total_bytes'] > 0:
                percent = d['downloaded_bytes'] / d['total_bytes'] * 100
                downloads[download_id]["progress"] = round(percent, 1)
            elif 'total_bytes_estimate' in d and d['total_bytes_estimate'] > 0:
                percent = d['downloaded_bytes'] / d['total_bytes_estimate'] * 100
                downloads[download_id]["progress"] = round(percent, 1)
        elif d['status'] == 'finished':
            downloads[download_id]["status"] = "processing"
        elif d['status'] == 'error':
            downloads[download_id]["status"] = "error"
            downloads[download_id]["error"] = str(d.get('error', '下载失败'))

    # 确定下载目录
    if download_dir:
        # 确保目录存在
        output_dir = Path(download_dir).resolve()  # 转换为绝对路径
        output_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(output_dir / '%(title)s-%(id)s.%(ext)s')
    else:
        output_dir = Path('videos').resolve()  # 转换为绝对路径
        output_template = str(output_dir / '%(title)s-%(id)s.%(ext)s')

    # 基本配置
    ydl_opts = {
        'progress_hooks': [progress_hook],
        'logger': DownloadLogger(),
        'outtmpl': output_template,
        'nocheckcertificate': True,
        'ignoreerrors': True,  # 忽略错误，继续下载
        'no_warnings': True,   # 不显示警告
        'quiet': True,         # 静默模式
        'socket_timeout': 30,  # 增加超时时间
        'retries': 10,         # 重试次数
        'fragment_retries': 10,# 片段重试次数
        'retry_sleep': 5,      # 重试间隔时间
        'ffmpeg_location': os.path.dirname(ffmpeg_path),  # 设置 FFmpeg 路径
    }

    # 根据格式类型设置不同的配置
    if format_type == "audio":
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'keepvideo': False,  # 不保留原始视频文件
        })
    else:  # 默认视频格式
        ydl_opts.update({
            'format': 'best',
            'extract_flat': True,  # 扁平化提取
            'force_generic_extractor': False,
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=True)
                
                if not info:
                    raise Exception("无法获取视频信息")
                
                if 'entries' in info:  # 处理播放列表
                    info = info['entries'][0]
                
                # 获取文件名和路径
                filename = ydl.prepare_filename(info)
                # 对于MP3格式，需要修改文件扩展名
                if format_type == "audio":
                    filename = os.path.splitext(filename)[0] + '.mp3'
                
                file_path = Path(filename).resolve()  # 转换为绝对路径
                
                # 检查文件是否存在
                if not file_path.exists():
                    raise Exception("下载完成，但找不到文件")
                
                # 获取文件大小
                file_size = file_path.stat().st_size
                
                # 保存视频信息
                video = Video(
                    video_id=info.get('id', ''),
                    title=info.get('title', '未知标题'),
                    author=info.get('uploader', '未知作者'),
                    duration=format_duration(info.get('duration', 0)),
                    description=info.get('description', '无描述'),
                    filepath=str(file_path),  # 保存绝对路径
                    size=format_size(file_size),
                    thumbnail=info.get('thumbnail', '')
                )
                
                # 更新视频列表
                videos = load_videos()
                videos.append(video.to_dict())
                save_videos(videos)
                
                downloads[download_id]["status"] = "completed"
                downloads[download_id]["video"] = video.to_dict()
            except yt_dlp.utils.DownloadError as e:
                downloads[download_id]["status"] = "error"
                downloads[download_id]["error"] = f"下载错误: {str(e)}"
            except yt_dlp.utils.ExtractorError as e:
                downloads[download_id]["status"] = "error"
                downloads[download_id]["error"] = f"提取错误: {str(e)}"
    except Exception as e:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = str(e)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    videos = load_videos()
    return templates.TemplateResponse("index.html", {"request": request, "videos": videos})

@app.post("/download")
async def download(
    background_tasks: BackgroundTasks, 
    video_url: str = Form(...), 
    download_dir: str = Form(None),
    format_type: str = Form("video")  # 默认为视频格式
):
    if not video_url or "youtube.com" not in video_url and "youtu.be" not in video_url:
        raise HTTPException(status_code=400, detail="请提供有效的YouTube视频链接")
    
    # 验证格式类型
    if format_type not in ["video", "audio"]:
        raise HTTPException(status_code=400, detail="不支持的格式类型")
    
    download_id = str(int(time.time()))
    background_tasks.add_task(download_video, video_url, download_id, download_dir, format_type)
    
    return {"download_id": download_id, "status": "started"}

@app.get("/download-status/{download_id}")
async def get_download_status(download_id: str):
    if download_id not in downloads:
        raise HTTPException(status_code=404, detail="下载任务不存在")
    
    return downloads[download_id]

@app.get("/video/{video_id}")
async def stream_video(video_id: str):
    videos = load_videos()
    video = next((v for v in videos if v["video_id"] == video_id), None)
    
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    
    filepath = Path(video["filepath"]).resolve()  # 转换为绝对路径
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    
    try:
        return FileResponse(filepath)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法访问文件: {str(e)}")

@app.get("/open-file-location/{video_id}")
async def open_file_location(video_id: str):
    videos = load_videos()
    video = next((v for v in videos if v["video_id"] == video_id), None)
    
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    
    filepath = Path(video["filepath"]).resolve()  # 转换为绝对路径
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    
    # 返回文件所在的目录路径
    return {"filepath": str(filepath.parent)}

@app.get("/open-folder/{path:path}")
async def open_folder(path: str):
    """在服务器上打开指定文件夹"""
    try:
        full_path = Path(path).resolve()  # 转换为绝对路径
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="目录不存在")
        
        # 在Windows上使用explorer打开文件夹
        if os.name == 'nt':
            try:
                import subprocess
                subprocess.run(['explorer', str(full_path)], check=True)
            except subprocess.CalledProcessError:
                # 如果explorer命令失败，尝试使用start命令
                os.system(f'start "" "{full_path}"')
        # 在macOS上使用open命令
        elif os.name == 'posix' and os.uname().sysname == 'Darwin':
            os.system(f'open "{full_path}"')
        # 在Linux上尝试使用xdg-open
        elif os.name == 'posix':
            os.system(f'xdg-open "{full_path}"')
        else:
            return {"error": "不支持的操作系统"}
        
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/videos")
async def get_videos():
    videos = load_videos()
    return videos

@app.get("/select-directory")
async def select_directory():
    """打开系统原生的目录选择对话框"""
    def open_dialog():
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        root.attributes('-topmost', True)  # 保持对话框在最前
        directory = filedialog.askdirectory()  # 打开目录选择对话框
        root.destroy()
        return directory

    # 在新线程中运行对话框，避免阻塞主线程
    thread = threading.Thread(target=lambda: setattr(thread, 'result', open_dialog()))
    thread.start()
    thread.join()
    
    selected_dir = getattr(thread, 'result', '')
    if not selected_dir:
        raise HTTPException(status_code=400, detail="未选择目录")
        
    # 统一路径分隔符为系统标准
    selected_dir = str(Path(selected_dir))
    return {"directory": selected_dir}

if __name__ == "__main__":
    # 确保 FFmpeg 已安装
    if not setup_ffmpeg():
        print("FFmpeg 设置失败，程序无法继续运行。")
        sys.exit(1)
    
    # 当直接运行时，执行uvicorn
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 
else:
    # 当被导入时，确保 FFmpeg 已设置
    setup_ffmpeg() 