import sys
sys.path.append("../")

from app.vision.engine import analyze_video

resultado = analyze_video("video_teste.mp4")
print(resultado)