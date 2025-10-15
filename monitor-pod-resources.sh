# client.hcl - Client-only configuration
data_dir = "/opt/nomad/data"
bind_addr = "0.0.0.0"

client {
  enabled = true
  
  # Server addresses (for client-only mode)
  servers = ["nomad-server-1:4647", "nomad-server-2:4647", "nomad-server-3:4647"]
  
  # Node class for targeting
  node_class = "compute"
  
  # Options for the client
  options {
    "driver.raw_exec.enable"    = "0"
    "driver.exec.enable"        = "1"
    "driver.docker.enable"      = "1"
    "docker.cleanup.image"      = "true"
    "docker.cleanup.image.delay" = "3h"
  }
  
  # Host volumes
  host_volume "logs" {
    path      = "/var/log/app"
    read_only = false
  }
  
  host_volume "shared" {
    path      = "/opt/nomad/shared"
    read_only = false
  }
  
  # Chroot environment (for exec driver)
  chroot_env {
    "/bin"            = "/bin"
    "/etc"            = "/etc"
    "/lib"            = "/lib"
    "/lib32"          = "/lib32"
    "/lib64"          = "/lib64"
    "/run/resolvconf" = "/run/resolvconf"
    "/sbin"           = "/sbin"
    "/usr"            = "/usr"
  }
}

# Docker driver plugin
plugin "docker" {
  config {
    enabled = true
    
    allow_caps = ["CHOWN", "NET_RAW", "SETUID", "SETGID"]
    
    volumes {
      enabled = true
    }
    
    gc {
      image       = true
      image_delay = "3m"
      container   = true
    }
  }
}

# Exec driver plugin
plugin "exec" {
  config {
    enabled = true
  }
}

advertise {
  http = "{{ GetPrivateIP }}"
  rpc  = "{{ GetPrivateIP }}"
  serf = "{{ GetPrivateIP }}"
}

log_level = "INFO"