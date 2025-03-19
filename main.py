from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
import re
import os
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="YouTube视频下载工具")

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 从环境变量获取API密钥，或使用默认值进行测试
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "your_rapidapi_key")

def extract_video_id(url):
    """从YouTube URL提取视频ID"""
    # 处理常规YouTube链接
    youtube_regex = r'(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(youtube_regex, url)
    
    if match:
        return match.group(1)
    return None

def get_video_info(video_url):
    """使用RapidAPI获取视频信息"""
    video_id = extract_video_id(video_url)
    
    if not video_id:
        raise HTTPException(status_code=400, detail="无效的YouTube链接")
    
    logger.info(f"提取到视频ID: {video_id}")
    
    # 使用RapidAPI的YouTube v3服务
    url = "https://youtube-v31.p.rapidapi.com/videos"
    
    querystring = {"part":"contentDetails,snippet,statistics","id":video_id}
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "youtube-v31.p.rapidapi.com"
    }
    
    try:
        logger.info("正在通过API获取视频信息")
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()  # 检查HTTP错误
        
        data = response.json()
        logger.info(f"API响应: {data}")
        
        if "items" not in data or len(data["items"]) == 0:
            raise HTTPException(status_code=404, detail="视频未找到")
        
        video_data = data["items"][0]
        snippet = video_data.get("snippet", {})
        content_details = video_data.get("contentDetails", {})
        
        # 获取可用的下载链接
        formats = get_download_links(video_id)
        
        return {
            "title": snippet.get("title", "未知标题"),
            "author": snippet.get("channelTitle", "未知作者"),
            "description": snippet.get("description", ""),
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            "duration": parse_duration(content_details.get("duration", "")),
            "formats": formats
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"请求错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"API请求失败: {str(e)}")
        except Exception as e:
        logger.error(f"处理错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"无法获取视频信息: {str(e)}")

def get_download_links(video_id):
    """获取视频下载链接"""
    # 使用另一个API获取下载链接
    url = "https://youtube-video-download-info.p.rapidapi.com/dl"
    
    querystring = {"id":video_id}
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "youtube-video-download-info.p.rapidapi.com"
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()
        
        data = response.json()
        logger.info(f"下载链接API响应状态: {data.get('status')}")
        
        formats = []
        
        # 处理不同格式
        if "link" in data:
            for format_key, format_info in data["link"].items():
                if isinstance(format_info, dict) and "url" in format_info:
                    formats.append({
                        "url": format_info["url"],
                        "ext": format_info.get("type", "mp4").split("/")[-1],
                        "format_note": format_key,
                        "resolution": format_info.get("qualityLabel", "Unknown"),
                        "filesize": "未知"
                    })
        
        # 如果没有找到链接，返回空列表
        if not formats:
            logger.warning("没有找到可用的下载链接")
            
        return formats
        
    except Exception as e:
        logger.error(f"获取下载链接错误: {str(e)}")
        # 返回空列表而不是抛出异常
        return []

def parse_duration(duration_str):
    """解析ISO 8601时长格式"""
    if not duration_str or not duration_str.startswith("PT"):
        return "未知"
    
    duration = duration_str[2:]  # 移除 "PT" 前缀
    hours, minutes, seconds = 0, 0, 0
    
    # 解析小时
    hour_pos = duration.find("H")
    if hour_pos != -1:
        hours = int(duration[:hour_pos])
        duration = duration[hour_pos + 1:]
    
    # 解析分钟
    minute_pos = duration.find("M")
    if minute_pos != -1:
        minutes = int(duration[:minute_pos])
        duration = duration[minute_pos + 1:]
    
    # 解析秒
    second_pos = duration.find("S")
    if second_pos != -1:
        seconds = int(duration[:second_pos])
    
    # 格式化时长
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/get-video-info")
async def get_info(video_url: str = Form(...)):
    if not video_url:
        raise HTTPException(status_code=400, detail="请提供YouTube视频链接")
    
    # 检查是否是YouTube链接
    if "youtube.com" not in video_url and "youtu.be" not in video_url:
        raise HTTPException(status_code=400, detail="请提供有效的YouTube视频链接")
    
    logger.info(f"收到请求: {video_url}")
    return get_video_info(video_url) 
