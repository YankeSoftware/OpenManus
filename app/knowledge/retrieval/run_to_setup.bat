@echo off
REM Install dependencies from requirements.txt
pip install -r requirements-hype.txt

REM Run the rebuild.sh script
bash ./rebuild.sh

REM Display success message
echo Installation and rebuild process completed successfully!
