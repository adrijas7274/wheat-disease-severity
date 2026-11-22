# Retrain both Phase 2 baselines one after the other (same defaults and seed as the first runs).
# Launched detached so it survives a closed terminal:
#   Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','scripts\retrain_baselines.ps1'
# Progress: experiments\retrain_<model>.log ; each run writes its own experiments\<timestamp>_<model>\ folder.
Set-Location (Split-Path $PSScriptRoot -Parent)
$python = ".venv\Scripts\python.exe"
foreach ($model in @("deeplabv3plus", "segformer")) {
    $p = Start-Process -FilePath $python -ArgumentList "-u", "-m", "src.train", "--config", "configs/config.yaml", "--model", $model `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput "experiments\retrain_$model.log" -RedirectStandardError "experiments\retrain_${model}_err.log"
    Add-Content -Path "experiments\retrain_status.log" -Value "$(Get-Date -Format s) $model exit code $($p.ExitCode)"
}
Add-Content -Path "experiments\retrain_status.log" -Value "$(Get-Date -Format s) all done"
