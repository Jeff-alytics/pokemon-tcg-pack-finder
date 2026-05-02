@echo off
echo ============================================
echo  Pokemon TCG - Graded Price Scraper (Local)
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] Running graded price scraper...
python build.py --score-only --with-graded
if %errorlevel% neq 0 (
    echo ERROR: Scraper failed.
    pause
    exit /b 1
)

echo.
echo [2/3] Committing updated graded.json...
git add data/graded.json
git diff --cached --quiet
if %errorlevel% equ 0 (
    echo No changes to graded.json - skipping commit.
) else (
    git commit -m "chore: refresh graded prices from local machine %date%"
    echo.
    echo [3/3] Pushing to GitHub...
    git push
)

echo.
echo Done! Graded data updated and pushed.
echo Pages will auto-deploy in ~15 seconds.
timeout /t 5
