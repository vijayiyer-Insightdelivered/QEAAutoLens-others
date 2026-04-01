#!/bin/bash
cd /home/site/wwwroot
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000
