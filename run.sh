#!/bin/bash
# EN: Local development server launcher for the FastAPI backend.
# KO: FastAPI 백엔드 로컬 개발 서버 실행 스크립트입니다.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
