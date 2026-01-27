#!/usr/bin/env python3
"""
Simple Upload Server for ComfyUI Models
Access at http://192.168.50.135:8989
"""

import os
from flask import Flask, request, render_template_string, jsonify, redirect
from werkzeug.utils import secure_filename
import shutil

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5GB max file size
UPLOAD_FOLDER = '/mnt/1TB-storage/ComfyUI/models/loras'

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>ComfyUI Model Uploader</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #1a1a1a;
            color: #fff;
        }
        h1 { color: #4dabf7; }
        .upload-area {
            border: 3px dashed #4dabf7;
            border-radius: 10px;
            padding: 50px;
            text-align: center;
            margin: 30px 0;
            background: #25262b;
            transition: all 0.3s;
        }
        .upload-area:hover, .upload-area.dragover {
            background: #2c2e33;
            border-color: #74c0fc;
        }
        input[type="file"] {
            display: none;
        }
        .btn {
            background: #228be6;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            margin: 10px;
            display: inline-block;
        }
        .btn:hover {
            background: #1c7ed6;
        }
        .file-list {
            margin-top: 20px;
            padding: 20px;
            background: #25262b;
            border-radius: 10px;
        }
        .file-item {
            padding: 10px;
            margin: 5px 0;
            background: #2c2e33;
            border-radius: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .progress {
            width: 100%;
            height: 30px;
            background: #2c2e33;
            border-radius: 5px;
            overflow: hidden;
            margin: 20px 0;
            display: none;
        }
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #228be6, #4dabf7);
            width: 0%;
            transition: width 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
        }
        .status {
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
            display: none;
        }
        .status.success {
            background: #2f9e44;
            display: block;
        }
        .status.error {
            background: #c92a2a;
            display: block;
        }
    </style>
</head>
<body>
    <h1>🚀 ComfyUI Model Uploader</h1>
    <p>Upload .safetensors models directly to the LoRA directory</p>

    <div class="upload-area" id="uploadArea">
        <p style="font-size: 48px;">📁</p>
        <p>Drag & Drop your .safetensors files here</p>
        <p style="color: #8c8fa3;">or</p>
        <label for="fileInput" class="btn">Browse Files</label>
        <input type="file" id="fileInput" accept=".safetensors" multiple>
    </div>

    <div class="progress" id="progressContainer">
        <div class="progress-bar" id="progressBar">0%</div>
    </div>

    <div class="status" id="status"></div>

    <div class="file-list">
        <h3>📦 Existing LoRA Models ({{ file_count }} files)</h3>
        <div style="max-height: 300px; overflow-y: auto;">
            {% for file in files %}
            <div class="file-item">
                <span>{{ file.name }}</span>
                <span style="color: #8c8fa3;">{{ file.size }}</span>
            </div>
            {% endfor %}
        </div>
    </div>

    <script>
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const progressContainer = document.getElementById('progressContainer');
        const progressBar = document.getElementById('progressBar');
        const status = document.getElementById('status');

        // Drag and drop
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });

        // File input
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });

        function handleFiles(files) {
            const validFiles = Array.from(files).filter(file =>
                file.name.endsWith('.safetensors')
            );

            if (validFiles.length === 0) {
                showStatus('Only .safetensors files are allowed!', 'error');
                return;
            }

            uploadFiles(validFiles);
        }

        async function uploadFiles(files) {
            progressContainer.style.display = 'block';

            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                const formData = new FormData();
                formData.append('file', file);

                try {
                    const xhr = new XMLHttpRequest();

                    xhr.upload.addEventListener('progress', (e) => {
                        if (e.lengthComputable) {
                            const percentComplete = (e.loaded / e.total) * 100;
                            progressBar.style.width = percentComplete + '%';
                            progressBar.textContent = Math.round(percentComplete) + '%';
                        }
                    });

                    xhr.addEventListener('load', () => {
                        if (xhr.status === 200) {
                            showStatus(`✅ Successfully uploaded: ${file.name}`, 'success');
                            setTimeout(() => location.reload(), 1500);
                        } else {
                            showStatus(`❌ Failed to upload: ${file.name}`, 'error');
                        }
                    });

                    xhr.addEventListener('error', () => {
                        showStatus(`❌ Error uploading: ${file.name}`, 'error');
                    });

                    xhr.open('POST', '/upload');
                    xhr.send(formData);

                } catch (error) {
                    showStatus(`❌ Error: ${error.message}`, 'error');
                }
            }
        }

        function showStatus(message, type) {
            status.className = 'status ' + type;
            status.textContent = message;
            status.style.display = 'block';
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    # List existing files
    files = []
    for filename in os.listdir(UPLOAD_FOLDER):
        if filename.endswith('.safetensors'):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            size = os.path.getsize(filepath)
            files.append({
                'name': filename,
                'size': f"{size / 1024 / 1024:.1f} MB"
            })

    files.sort(key=lambda x: x['name'])

    return render_template_string(HTML_TEMPLATE,
                                 files=files,
                                 file_count=len(files))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.endswith('.safetensors'):
        return jsonify({'error': 'Only .safetensors files allowed'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    # Save the file
    file.save(filepath)

    print(f"✅ Uploaded: {filename} ({os.path.getsize(filepath) / 1024 / 1024:.1f} MB)")

    return jsonify({
        'success': True,
        'filename': filename,
        'path': filepath
    })

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    print("🚀 Starting ComfyUI Model Upload Server")
    print(f"📁 Upload directory: {UPLOAD_FOLDER}")
    print(f"🌐 Access at: http://192.168.50.135:8989")
    print("=" * 50)
    app.run(host='0.0.0.0', port=8989, debug=False)