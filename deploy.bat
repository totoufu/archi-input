@echo off
chcp 65001 > nul
echo.
echo ========================================
echo   Archi Input - Deploy to VPS
echo ========================================
echo.

cd /d C:\Users\hirat\.gemini\antigravity\scratch\archi-input

echo [1/3] Git commit ^& push...
git add -A
set /p MSG="コミットメッセージ (Enter=update): "
if "%MSG%"=="" set MSG=update
git commit -m "%MSG%"
git push

echo.
echo [2/3] VPS に SSH 接続して更新します...
echo        (パスワードを入力してください)
echo.
ssh root@163.44.119.69 "cd /opt/archi-input && git pull && systemctl restart archi-input && echo '' && echo '=== Deploy OK! ===' && systemctl status archi-input --no-pager -l | head -5"

echo.
echo [3/3] 完了！
echo   ローカル: http://127.0.0.1:5000
echo   VPS:      http://163.44.119.69
echo ========================================
pause
