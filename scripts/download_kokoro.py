import os
import urllib.request
import sys

def download_file(url, filepath):
    # Ensure directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    if os.path.exists(filepath):
        print(f"File {filepath} already exists. Skipping download.")
        return

    print(f"Downloading {url} to {filepath}...")
    
    def reporthook(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = readsofar * 1e2 / totalsize
            s = f"\r{percent:5.1f}% {readsofar / 1e6:.2f} MB / {totalsize / 1e6:.2f} MB"
            sys.stderr.write(s)
            if readsofar >= totalsize: # near the end
                sys.stderr.write("\n")
        else: # total size is unknown
            sys.stderr.write(f"\r{readsofar / 1e6:.2f} MB")

    try:
        urllib.request.urlretrieve(url, filepath, reporthook)
        print(f"Successfully downloaded {filepath}")
    except Exception as e:
        print(f"\nError downloading {url}: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        sys.exit(1)

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models_dir = os.path.join(base_dir, "models", "kokoro")
    
    # We use the official thewh1teagle kokoro-onnx v1.0 release files
    onnx_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
    voices_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
    
    download_file(onnx_url, os.path.join(models_dir, "kokoro-v1.0.onnx"))
    download_file(voices_url, os.path.join(models_dir, "voices-v1.0.bin"))
    
    print("All downloads complete!")
