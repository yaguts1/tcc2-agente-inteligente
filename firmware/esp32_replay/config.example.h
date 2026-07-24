#pragma once
// Configuração de rede/servidor do firmware ESP32 (replayer).
//
// SETUP (obrigatório antes de compilar/flashar):
//   1. Copie este arquivo para `config.h` na MESMA pasta:
//        cp config.example.h config.h
//   2. Edite `config.h` com os valores da sua rede.
//
// `config.h` é git-ignored — NUNCA comite credenciais reais no repositório.
// (Os sketches .ino incluem "config.h", não este arquivo de exemplo.)

#define WIFI_SSID   "SUA_REDE_WIFI"
#define WIFI_SENHA  "SUA_SENHA_WIFI"

// IP ou host do backend na sua LAN — sem esquema http:// e sem a porta.
#define SERVER_IP   "192.168.0.10"
#define SERVER_PORT 8000
