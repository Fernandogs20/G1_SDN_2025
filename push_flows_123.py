#!/usr/bin/python3
# -*- coding: utf-8 -*-

import requests

# ==========================
# Static Flow Pusher
# ==========================
FLOOD = "http://192.168.201.200:8080/wm/staticflowpusher/json"

# ==========================
# DPIDs
# ==========================
SW1 = "00:00:06:4e:14:04:51:42"
SW2 = "00:00:2e:ab:68:47:c8:4c"   
SW3 = "00:00:5e:ee:21:ee:54:48"
SW4 = "00:00:aa:44:56:b4:2f:4c"

# ==========================
# PUERTOS FÍSICOS
# ==========================

# SW3
SW3_TO_SW1 = 1          # ens4
SW3_TO_SW2 = 2          # ens5
SW3_TO_SW4 = 3          # ens6
SW3_H2      = 4         # ens8 (10.0.0.2)
SW3_H1      = 5         # ens7 (10.0.0.1)
SW3_H3      = 6         # ens9 (10.0.0.3)
SW3_H4      = 7         # ens10 (10.0.0.4)

SW3_HOSTS = {
    "h1": {"ip": "10.0.0.1", "port": SW3_H1},
    "h2": {"ip": "10.0.0.2", "port": SW3_H2},
    "h3": {"ip": "10.0.0.3", "port": SW3_H3},
    "h4": {"ip": "10.0.0.4", "port": SW3_H4},
}

# SW4
SW4_TO_SW1 = 1          # ens4
SW4_TO_SW2 = 2          # ens5
SW4_TO_SW3 = 3          # ens6
SW4_H5      = 4         # ens7 
SW4_H6      = 5         # ens8 
SW4_H7      = 6         # ens9 (10.0.0.7)
SW4_H8      = 7         # ens10 (10.0.0.8)

H7 = {"ip": "10.0.0.7", "port": SW4_H7}
H8 = {"ip": "10.0.0.8", "port": SW4_H8}

# SW1
SW1_TO_CTRL = 1         # ens4
SW1_TO_SW2  = 2         # ens5
SW1_TO_SW3  = 3         # ens6
SW1_TO_SW4  = 4         # ens7

CTRL_IP = "10.0.0.254"

# ==========================
# Función push
# ==========================
def push(flow):
    r = requests.post(FLOOD, json=flow)
    print(f"[{r.status_code}] {flow['name']}")
    if r.status_code != 200:
        print(r.text)


# ==========================
# INSTALACIÓN DE FLOWS
# ==========================
def install():

    # =======================================================
    # SW3: h1–h4 <-> (h7,h8,controller)
    # =======================================================
    print("\n===== INSTALANDO FLOWS EN SW3 =====\n")

    # 1) Tráfico QUE LLEGA DESDE SW1 o SW4 hacia h1–h4
    for h, data in SW3_HOSTS.items():
        hip = data["ip"]
        hport = data["port"]

        # ARP desde SW1 o SW4 hacia hX
        for inport in [SW3_TO_SW1, SW3_TO_SW4]:
            push({
                "switch": SW3,
                "name": f"sw3_arp_to_{h}_from_{inport}",
                "priority": 40000,
                "in_port": inport,
                "eth_type": 2054,
                "arp_tpa": hip,
                "actions": f"output={hport}"
            })

        # IPv4 desde SW1 o SW4 hacia hX
        for inport in [SW3_TO_SW1, SW3_TO_SW4]:
            push({
                "switch": SW3,
                "name": f"sw3_ipv4_to_{h}_from_{inport}",
                "priority": 40000,
                "in_port": inport,
                "eth_type": 2048,
                "ipv4_dst": hip,
                "actions": f"output={hport}"
            })

    # 2) Tráfico que SALE de h1–h4 hacia h7, h8 y controller
    DESTINOS_SW3 = [H7["ip"], H8["ip"], CTRL_IP]

    for h, data in SW3_HOSTS.items():
        hip_src = data["ip"]
        in_port = data["port"]

        for dip in DESTINOS_SW3:
            # hacia h7/h8 -> sale por SW3_TO_SW4
            # hacia controller -> sale por SW3_TO_SW1
            outp = SW3_TO_SW4 if dip in [H7["ip"], H8["ip"]] else SW3_TO_SW1

            # ARP
            push({
                "switch": SW3,
                "name": f"sw3_{h}_arp_to_{dip}",
                "priority": 40000,
                "in_port": in_port,
                "eth_type": 2054,
                "arp_tpa": dip,
                "actions": f"output={outp}"
            })

            # IPv4
            push({
                "switch": SW3,
                "name": f"sw3_{h}_ipv4_to_{dip}",
                "priority": 40000,
                "in_port": in_port,
                "eth_type": 2048,
                "ipv4_src": hip_src,
                "ipv4_dst": dip,
                "actions": f"output={outp}"
            })

    # Nota: NO hay reglas donde in_port=puerto de host y dst=IP de OTRO host de SW3,
    # así que h1–h4 NO se pueden hablar entre sí.


    # =======================================================
    # SW4: h7–h8 <-> h1–h4, controller y entre ellos
    # =======================================================
    print("\n===== INSTALANDO FLOWS EN SW4 =====\n")

    # 1) Tráfico que LLEGA desde SW3 o SW1 hacia h7/h8
    for dev in [H7, H8]:
        ip = dev["ip"]
        port = dev["port"]

        for inport in [SW4_TO_SW3, SW4_TO_SW1]:
            # ARP
            push({
                "switch": SW4,
                "name": f"sw4_arp_to_{ip}_from_{inport}",
                "priority": 40000,
                "in_port": inport,
                "eth_type": 2054,
                "arp_tpa": ip,
                "actions": f"output={port}"
            })
            # IPv4
            push({
                "switch": SW4,
                "name": f"sw4_ipv4_to_{ip}_from_{inport}",
                "priority": 40000,
                "in_port": inport,
                "eth_type": 2048,
                "ipv4_dst": ip,
                "actions": f"output={port}"
            })

    # 2) Tráfico que SALE de h7/h8 hacia h1–h4 y controller
    DEST_HOSTS_SW3 = [d["ip"] for d in SW3_HOSTS.values()]

    for dev in [H7, H8]:
        ip_src = dev["ip"]
        in_port = dev["port"]

        # hacia h1–h4 (pasan por SW3)
        for dip in DEST_HOSTS_SW3:

            # ARP
            push({
                "switch": SW4,
                "name": f"sw4_{ip_src}_arp_to_{dip}",
                "priority": 40000,
                "in_port": in_port,
                "eth_type": 2054,
                "arp_tpa": dip,
                "actions": f"output={SW4_TO_SW3}"
            })

            # IPv4
            push({
                "switch": SW4,
                "name": f"sw4_{ip_src}_ipv4_to_{dip}",
                "priority": 40000,
                "in_port": in_port,
                "eth_type": 2048,
                "ipv4_src": ip_src,
                "ipv4_dst": dip,
                "actions": f"output={SW4_TO_SW3}"
            })

        # hacia controller
        push({
            "switch": SW4,
            "name": f"sw4_{ip_src}_arp_to_ctrl",
            "priority": 40000,
            "in_port": in_port,
            "eth_type": 2054,
            "arp_tpa": CTRL_IP,
            "actions": f"output={SW4_TO_SW1}"
        })
        push({
            "switch": SW4,
            "name": f"sw4_{ip_src}_ipv4_to_ctrl",
            "priority": 40000,
            "in_port": in_port,
            "eth_type": 2048,
            "ipv4_src": ip_src,
            "ipv4_dst": CTRL_IP,
            "actions": f"output={SW4_TO_SW1}"
        })

    # 3) Tráfico interno h7 <-> h8 (mismo switch)
    # h7 -> h8
    push({
        "switch": SW4,
        "name": "sw4_h7_to_h8_arp",
        "priority": 40000,
        "in_port": SW4_H7,
        "eth_type": 2054,
        "arp_tpa": H8["ip"],
        "actions": f"output={SW4_H8}"
    })
    push({
        "switch": SW4,
        "name": "sw4_h7_to_h8_ipv4",
        "priority": 40000,
        "in_port": SW4_H7,
        "eth_type": 2048,
        "ipv4_dst": H8["ip"],
        "actions": f"output={SW4_H8}"
    })

    # h8 -> h7
    push({
        "switch": SW4,
        "name": "sw4_h8_to_h7_arp",
        "priority": 40000,
        "in_port": SW4_H8,
        "eth_type": 2054,
        "arp_tpa": H7["ip"],
        "actions": f"output={SW4_H7}"
    })
    push({
        "switch": SW4,
        "name": "sw4_h8_to_h7_ipv4",
        "priority": 40000,
        "in_port": SW4_H8,
        "eth_type": 2048,
        "ipv4_dst": H7["ip"],
        "actions": f"output={SW4_H7}"
    })


    # =======================================================
    # SW1: solo “router” entre SW3/SW4 y controller
    # =======================================================
    print("\n===== INSTALANDO FLOWS EN SW1 =====\n")

    # 1) Tráfico que llega DESDE SW3/SW4 hacia controller
    for inport in [SW1_TO_SW3, SW1_TO_SW4]:
        # ARP hacia controller
        push({
            "switch": SW1,
            "name": f"sw1_arp_to_ctrl_from_{inport}",
            "priority": 40000,
            "in_port": inport,
            "eth_type": 2054,
            "arp_tpa": CTRL_IP,
            "actions": f"output={SW1_TO_CTRL}"
        })
        # IPv4 hacia controller
        push({
            "switch": SW1,
            "name": f"sw1_ipv4_to_ctrl_from_{inport}",
            "priority": 40000,
            "in_port": inport,
            "eth_type": 2048,
            "ipv4_dst": CTRL_IP,
            "actions": f"output={SW1_TO_CTRL}"
        })

    # 2) Tráfico que LLEGA desde controller hacia hosts
    DESTINOS_SW1 = [
        # hacia h1–h4 por SW3
        (SW1_TO_SW3, SW3_HOSTS["h1"]["ip"]),
        (SW1_TO_SW3, SW3_HOSTS["h2"]["ip"]),
        (SW1_TO_SW3, SW3_HOSTS["h3"]["ip"]),
        (SW1_TO_SW3, SW3_HOSTS["h4"]["ip"]),
        # hacia h7–h8 por SW4
        (SW1_TO_SW4, H7["ip"]),
        (SW1_TO_SW4, H8["ip"]),
    ]

    for outp, dip in DESTINOS_SW1:
        # ARP
        push({
            "switch": SW1,
            "name": f"sw1_ctrl_arp_to_{dip}",
            "priority": 40000,
            "in_port": SW1_TO_CTRL,
            "eth_type": 2054,
            "arp_tpa": dip,
            "actions": f"output={outp}"
        })
        # IPv4
        push({
            "switch": SW1,
            "name": f"sw1_ctrl_ipv4_to_{dip}",
            "priority": 40000,
            "in_port": SW1_TO_CTRL,
            "eth_type": 2048,
            "ipv4_dst": dip,
            "actions": f"output={outp}"
        })


# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    install()