from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import yt_dlp

app = FastAPI(title="YouTube视频下载工具")

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_video_info(video_url: str):
    """获取视频信息和下载链接"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,  # 改为False以获取完整信息
        'no_check_certificates': True,
        'ignoreerrors': True,
        # 添加以下配置来处理反爬虫
        'cookiesfrombrowser': ('chrome',),  # 尝试从Chrome获取cookies
        'extractor_args': {'youtube': {
            'player_client': ['android'],  # 使用android客户端
            'player_skip': ['webpage', 'config'],  # 跳过一些检查
        }},
        # 设置请求头
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            if not info:
                raise HTTPException(status_code=400, detail="无法获取视频信息")
            
            # 获取可用的格式
            formats = []
            if 'formats' in info:
                for f in info['formats']:
                    # 只获取直接可用的视频链接
                    if ('url' in f and 'ext' in f and 'format_note' in f 
                        and not f.get('acodec') == 'none'  # 排除仅视频格式
                        and not f.get('vcodec') == 'none'  # 排除仅音频格式
                    ):
                        format_info = {
                            'url': f['url'],
                            'ext': f['ext'],
                            'format_note': f['format_note'],
                            'filesize': format_filesize(f.get('filesize', 0)),
                            'resolution': f.get('resolution', 'Unknown')
                        }
                        formats.append(format_info)
            
            return {
                'title': info.get('title', '未知标题'),
                'author': info.get('uploader', '未知作者'),
                'duration': format_duration(info.get('duration', 0)),
                'thumbnail': info.get('thumbnail', ''),
                'formats': formats
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def format_filesize(bytes):
    """格式化文件大小"""
    if bytes == 0:
        return 'Unknown'
    units = ['B', 'KB', 'MB', 'GB']
    size = float(bytes)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"

def format_duration(seconds):
    """格式化视频时长"""
    if not seconds:
        return 'Unknown'
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/get-video-info")
async def get_info(video_url: str = Form(...)):
    if not video_url or "youtube.com" not in video_url and "youtu.be" not in video_url:
        raise HTTPException(status_code=400, detail="请提供有效的YouTube视频链接")
    
    return get_video_info(video_url) 
