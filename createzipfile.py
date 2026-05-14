import zipfile
import base64
import io
import sys
import os 

param_1 = sys.argv[1]

def zip_directory(folder_path):
    try:
        zipbuffer = io.BytesIO()
        with zipfile.ZipFile(zipbuffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for folder_name, subfolers, filenames in os.walk(folder_path):
                for filename in filenames: 
                    file_path = os.path.join(folder_name, filename)
                    arcname = os.path.relpath(file_path, folder_path)
                    zf.write(file_path, arcname)
        zip_data = zipbuffer.getvalue()
        base64_encoded = base64.b64encode(zip_data)
        base64_decoded = base64.b64decode(base64_encoded)
        #từ dữ liêu decode thì làm sao có thể lưu dữ liệu vào 1 filezip ở buffer sau đó extractall thành file bình thường 
        filezip = io.BytesIO(base64_decoded)
        with zipfile.ZipFile(filezip, 'r') as zf:
            zf.extractall("fileneww")
    except Exception as e:
        print(f"[!] Lỗi khi nén thư mục: {e}")

    
if __name__ == "__main__":
    zip_directory(param_1)
