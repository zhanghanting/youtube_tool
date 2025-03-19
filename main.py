from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import yt_dlp
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="YouTube视频下载工具")

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_video_info(video_url: str):
    """获取视频信息和下载链接"""
    ydl_opts = {
        'format': 'best',  # 只获取最佳质量版本
        'quiet': False,    # 显示详细日志
        'no_warnings': False,
        'extract_flat': False,
        'ignoreerrors': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # 首先尝试获取基本信息
                logger.info(f"正在获取视频信息: {video_url}")
                info = ydl.extract_info(video_url, download=False)
                
                if not info:
                    logger.error("无法获取视频信息")
                    raise HTTPException(status_code=400, detail="无法获取视频信息")
                
                # 记录获取到的信息
                logger.info(f"成功获取视频信息: {info.get('title', '未知标题')}")
                
                # 构建格式列表
                formats = []
                if 'formats' in info:
                    for f in info['formats']:
                        # 只获取包含URL的格式
                        if 'url' in f:
                            format_info = {
                                'url': f['url'],
                                'ext': f.get('ext', 'unknown'),
                                'format_note': f.get('format_note', 'unknown'),
                                'filesize': format_filesize(f.get('filesize', 0)),
                                'resolution': f.get('resolution', 'unknown'),
                                'format_id': f.get('format_id', 'unknown')
                            }
                            formats.append(format_info)
                            logger.info(f"找到格式: {format_info['format_note']} - {format_info['resolution']}")
                
                if not formats:
                    logger.warning("没有找到可用的下载格式")
                
                return {
                    'title': info.get('title', '未知标题'),
                    'author': info.get('uploader', '未知作者'),
                    'duration': format_duration(info.get('duration', 0)),
                    'thumbnail': info.get('thumbnail', ''),
                    'formats': formats
                }
                
            except Exception as e:
                logger.error(f"提取视频信息时出错: {str(e)}")
                # 尝试使用备用方法
                info = ydl.extract_info(video_url, download=False, process=False)
                if info:
                    return {
                        'title': info.get('title', '未知标题'),
                        'author': info.get('uploader', '未知作者'),
                        'duration': format_duration(info.get('duration', 0)),
                        'thumbnail': info.get('thumbnail', ''),
                        'formats': [{
                            'url': info.get('url', ''),
                            'ext': info.get('ext', 'mp4'),
                            'format_note': 'Best quality',
                            'filesize': 'Unknown',
                            'resolution': info.get('resolution', 'Unknown')
                        }]
                    }
                raise
                
    except Exception as e:
        logger.error(f"处理视频时出错: {str(e)}")
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
    
    logger.info(f"收到请求: {video_url}")
    return get_video_info(video_url) 
