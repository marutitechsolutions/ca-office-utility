import os
from PIL import Image
from typing import List

class ImageEngine:
    @staticmethod
    def images_to_pdf(image_paths: List[str], output_path: str) -> None:
        """
        Converts multiple images to a single PDF.
        Auto-scales/fits images to standard A4 dimensions while maintaining high DPI/quality.
        A4 at 72 DPI is roughly 595 x 842 points.
        """
        # A4 standard sizing in points
        a4_width, a4_height = 595.276, 841.890
        
        pdf_pages: List[Image.Image] = []
        for path in image_paths:
            img = Image.open(path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            # Calculate scaling factor to fit within A4
            img_width, img_height = img.size
            ratio_w = a4_width / img_width
            ratio_h = a4_height / img_height
            
            # Choose the minimum ratio to ensure the whole image fits in the page
            ratio = min(ratio_w, ratio_h)
            
            new_width = int(img_width * ratio)
            new_height = int(img_height * ratio)
            
            # Create a blank A4 white canvas
            canvas = Image.new("RGB", (int(a4_width), int(a4_height)), "white")
            
            # Resize image with high quality
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Center the image on the canvas
            offset_x = (int(a4_width) - new_width) // 2
            offset_y = (int(a4_height) - new_height) // 2
            
            canvas.paste(img_resized, (offset_x, offset_y))
            pdf_pages.append(canvas)
            
        if pdf_pages:
            pdf_pages[0].save(
                output_path, 
                "PDF", 
                resolution=100.0, 
                save_all=True, 
                append_images=pdf_pages[1:]
            )
    @staticmethod
    def compress_image(image_path: str, output_path: str, target_kb: int) -> None:
        """
        Compresses an image to be as close to target_kb as possible without dropping below.
        Uses an iterative binary search or step-down approach for quality and scaling.
        """
        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        target_bytes = target_kb * 1024
        
        # Test original save size first
        temp_path = output_path + ".tmp"
        img.save(temp_path, format="JPEG", quality=95)
        current_size = os.path.getsize(temp_path)
        
        if current_size <= target_bytes:
            # Already small enough, just rename and return
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_path, output_path)
            return
            
        # We need to compress
        quality = 90
        scale = 1.0
        best_size_diff = float('inf')
        
        # Iteratively step down quality, then resolution
        while quality >= 20 and scale >= 0.3:
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            resized.save(temp_path, format="JPEG", quality=quality, optimize=True)
            
            size = os.path.getsize(temp_path)
            
            if size <= target_bytes:
                # We met the goal
                break
                
            # Decrease parameters for next loop based on how far we are
            if size > target_bytes * 1.5:
                # Way too big, decrease scale
                scale -= 0.1
            else:
                # Getting close, drop quality
                quality -= 10
                
        # Final save
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(temp_path, output_path)
