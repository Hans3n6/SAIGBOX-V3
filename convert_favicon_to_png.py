#!/usr/bin/env python3
import subprocess
import sys
import os

# Try different methods to convert SVG to PNG

def try_cairosvg():
    """Try using cairosvg library"""
    try:
        import cairosvg
        print("Using cairosvg to convert...")
        cairosvg.svg2png(url='/Users/marcushansen/SAIGBOX-V3/static/saigbox-favicon.svg', 
                         write_to='/Users/marcushansen/Desktop/saigbox-favicon.png',
                         output_width=512,
                         output_height=512)
        return True
    except ImportError:
        print("cairosvg not installed")
        return False
    except Exception as e:
        print(f"cairosvg error: {e}")
        return False

def try_pillow():
    """Try using Pillow with svglib"""
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM
        print("Using svglib/reportlab to convert...")
        drawing = svg2rlg('/Users/marcushansen/SAIGBOX-V3/static/saigbox-favicon.svg')
        renderPM.drawToFile(drawing, '/Users/marcushansen/Desktop/saigbox-favicon.png', fmt="PNG")
        return True
    except ImportError:
        print("svglib/reportlab not installed")
        return False
    except Exception as e:
        print(f"svglib error: {e}")
        return False

def try_rsvg():
    """Try using rsvg-convert command line tool"""
    try:
        result = subprocess.run(['which', 'rsvg-convert'], capture_output=True, text=True)
        if result.returncode == 0:
            print("Using rsvg-convert...")
            subprocess.run([
                'rsvg-convert', 
                '-w', '512',
                '-h', '512',
                '/Users/marcushansen/SAIGBOX-V3/static/saigbox-favicon.svg',
                '-o', '/Users/marcushansen/Desktop/saigbox-favicon.png'
            ])
            return True
    except:
        pass
    return False

def create_png_manually():
    """Create a simple PNG representation using PIL"""
    try:
        from PIL import Image, ImageDraw
        print("Creating PNG manually with PIL...")
        
        # Create a 512x512 image with transparent background
        img = Image.new('RGBA', (512, 512), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw a green leaf shape (simplified)
        # This is a simplified representation of the leaf
        leaf_color = (127, 201, 127, 255)  # #7fc97f with full opacity
        
        # Draw main leaf body (ellipse)
        draw.ellipse([100, 50, 400, 350], fill=leaf_color)
        
        # Draw leaf stem
        draw.rectangle([240, 350, 270, 450], fill=leaf_color)
        
        # Add some leaf veins
        draw.line([(256, 100), (256, 350)], fill=(100, 175, 100, 255), width=3)
        draw.line([(200, 150), (256, 200)], fill=(100, 175, 100, 255), width=2)
        draw.line([(312, 150), (256, 200)], fill=(100, 175, 100, 255), width=2)
        draw.line([(200, 250), (256, 300)], fill=(100, 175, 100, 255), width=2)
        draw.line([(312, 250), (256, 300)], fill=(100, 175, 100, 255), width=2)
        
        # Save the image
        img.save('/Users/marcushansen/Desktop/saigbox-favicon.png', 'PNG')
        return True
    except ImportError:
        print("PIL/Pillow not installed")
        return False
    except Exception as e:
        print(f"PIL error: {e}")
        return False

# Try different methods in order of preference
if not try_cairosvg():
    if not try_rsvg():
        if not try_pillow():
            if not create_png_manually():
                print("Unable to convert SVG to PNG")
                print("\nTo convert manually, you can:")
                print("1. Install cairosvg: pip install cairosvg")
                print("2. Or install rsvg: brew install librsvg")
                print("3. Or use an online converter")
                sys.exit(1)

if os.path.exists('/Users/marcushansen/Desktop/saigbox-favicon.png'):
    print("\n✅ Successfully created: ~/Desktop/saigbox-favicon.png")
    # Get file size
    size = os.path.getsize('/Users/marcushansen/Desktop/saigbox-favicon.png')
    print(f"File size: {size:,} bytes")
else:
    print("❌ Failed to create PNG file")