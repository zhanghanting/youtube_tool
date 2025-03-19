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
        'extract_flat': True,
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
                    if 'url' in f and 'ext' in f and 'format_note' in f:
                        format_info = {
                            'url': f['url'],
                            'ext': f['ext'],
                            'format_note': f['format_note'],
                            'filesize': f.get('filesize', 'Unknown'),
                            'resolution': f.get('resolution', 'Unknown')
                        }
                        formats.append(format_info)
            
            return {
                'title': info.get('title', '未知标题'),
                'author': info.get('uploader', '未知作者'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'formats': formats
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/get-video-info")
async def get_info(video_url: str = Form(...)):
    if not video_url or "youtube.com" not in video_url and "youtu.be" not in video_url:
        raise HTTPException(status_code=400, detail="请提供有效的YouTube视频链接")
    
    return get_video_info(video_url) 
