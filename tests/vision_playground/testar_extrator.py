import sys
sys.path.append("../")

from app.vision.frame_extractor import extrair_frames

frames = extrair_frames("video_teste.mp4")
print(f"Total de frames extraídos: {len(frames)}")
print(f"Shape de um frame: {frames[0].shape}")