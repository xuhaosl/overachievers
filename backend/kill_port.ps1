# 杀掉占用 8100 端口的残留服务进程（vbs 启动 uvicorn 前调用）
Get-NetTCPConnection -LocalPort 8100 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
