# Copiar a config.ps1 y editar (config.ps1 no se sube a git)
@{
    VpsIp      = "123.456.789.0"      # IP publica del VPS
    SshUser    = "root"               # o ubuntu en algunas imagenes
    ApiDomain  = "api.tudominio.com"  # registro DNS tipo A -> VpsIp
    RepoPath   = "~/Anti-Bots"        # ruta en el servidor
    SshKeyPath = ""                   # opcional: C:\Users\tu\.ssh\id_ed25519
}
