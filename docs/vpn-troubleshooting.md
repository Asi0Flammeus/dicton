# dicton + VPN

Si dicton renvoie `Client error '403 Forbidden'` sur `api.groq.com` (en transcription ou pendant le wizard à l'étape clé Groq) et que tu as un VPN actif, c'est lui le coupable. Cette page explique pourquoi et comment contourner par client.

## Pourquoi Groq bloque les VPN

L'API Groq applique deux filtres au niveau IP :

- **Blocklists d'ASN** : les plages d'IP appartenant aux fournisseurs VPN commerciaux et aux gros datacenters (OVH, DO, Hetzner…) renvoient 403 immédiat — même sur un `GET /v1/models` vide. C'est la cause la plus fréquente.
- **Géoblocage** : sanctions US OFAC, certains pays renvoient 403. Si ton serveur VPN sort d'un pays sur la liste rouge, idem.

Le 403 vient donc du serveur, indépendamment de ta clé et du payload. Le seul fix réseau : faire sortir le trafic dicton **hors** du tunnel.

## La solution : split tunneling par app

Le split tunneling permet d'exclure une application spécifique du VPN — son trafic emprunte la route par défaut (ton wifi/ethernet) tandis que le reste du système reste dans le tunnel. C'est sans risque côté privacy pour dicton : Groq voit de toute façon ton audio et tes transcriptions en clair, le VPN ne te protège rien à ce niveau.

L'exclusion à appliquer : le binaire `dicton` (ou le wrapper Python qui le lance).

## Par client VPN

Les sections sont triées par ergonomie de configuration, du plus simple au plus pénible.

### Mullvad — Linux, macOS, Windows

Le plus propre des trois OS. CLI cohérente partout.

```bash
# Linux : lance dicton dans un cgroup exclu
mullvad-exclude dicton --foreground

# macOS / Windows : ajoute le binaire à la liste d'exclusion
mullvad split-tunnel add "$(which dicton)"
mullvad split-tunnel set enabled
```

Pour rendre persistant côté Linux, patcher l'unit systemd :

```ini
# ~/.config/systemd/user/dicton.service
ExecStart=/usr/bin/mullvad-exclude /home/<user>/.local/bin/dicton --foreground
```

Puis `systemctl --user daemon-reload && systemctl --user restart dicton`.

Doc : https://mullvad.net/en/help/split-tunneling-with-the-mullvad-app

### PIA (Private Internet Access) — Linux, macOS, Windows

Même CLI sur les trois OS, c'est la meilleure expérience scripting.

```bash
piactl set --add-exclude-app "$(which dicton)"
piactl set --route-app-exclusions true
```

Pour retirer : `piactl set --remove-exclude-app /chemin/dicton`.

Doc : https://helpdesk.privateinternetaccess.com → Split tunneling.

### IVPN — Linux, Windows (pas macOS)

macOS abandonné depuis qu'Apple a banni les kexts. Sur Linux/Windows :

```bash
# Linux : active le split tunnel global puis lance dicton dedans
ivpn splittun -on
ivpn exclude /home/<user>/.local/bin/dicton --foreground

# Persistance systemd
# ExecStart=/usr/bin/ivpn exclude /home/<user>/.local/bin/dicton --foreground
```

Sur Windows, l'app GUI gère la liste : _Settings → Split Tunnel → Add application → dicton.exe_.

Doc : https://github.com/ivpn/desktop-app-cli

### NordVPN — Linux (allowlist IP), Windows (per-app), macOS (exclude-only)

Sur Linux, NordVPN n'a pas de vrai per-app split — mais on peut allowlister le domaine Groq (réseau-level) :

```bash
nordvpn set splittunnel on
nordvpn allowlist add subnet 0.0.0.0/0 --port 443  # trop large, à éviter
# Mieux : résoudre l'IP de api.groq.com et l'allowlister
# (l'IP peut changer, à refaire si Groq tourne ses entrées Cloudflare)
```

Sur Windows : GUI _Split Tunneling → Add app → dicton.exe_.

Sur macOS : seul l'exclude-only fonctionne, à activer dans la GUI.

### ProtonVPN — Linux, macOS, Windows

Per-app split tunneling GA en septembre 2025 sur les trois OS, configuré via le nouveau daemon (l'ancien `protonvpn-cli` est obsolète pour cette feature). Configuration via GUI uniquement à ce stade :

_Settings → Connection → Advanced features → Split tunneling → Apps → Ajouter `dicton`_.

Doc : https://protonvpn.com/support/protonvpn-split-tunneling

### ExpressVPN — Linux, macOS, Windows

Linux a reçu un gros rewrite Qt en 2025 avec le split tunneling. Activation CLI + ajout d'apps via GUI :

```bash
expressvpn preferences set split_tunnel true
# Puis ouvrir la GUI pour ajouter dicton à la liste
```

### Surfshark — Windows (GUI per-app), Linux (par IP uniquement), macOS (non supporté)

Sur Linux le CLI ne gère que l'allowlist IP/domaine :

```bash
surfshark-vpn bypasser add api.groq.com
```

Sur Windows, _Bypasser → Bypass VPN → Add application → dicton.exe_.

Pas de split tunneling sur macOS.

### Cloudflare WARP (1.1.1.1) — Linux, macOS, Windows

Pas de per-app sur desktop, seulement par IP/CIDR/domaine :

```bash
warp-cli tunnel host add api.groq.com
```

(L'utilisateur doit redémarrer le tunnel pour que ça prenne.)

Doc : https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/cloudflare-one-client/configure/route-traffic/split-tunnels/

### Tailscale — particulier

Tailscale n'est pas un VPN traffic par défaut : il ne route que les IPs de ton tailnet. Le 403 Groq n'apparaît que si tu as activé un **exit-node**. Désactivation :

```bash
tailscale set --exit-node=
```

Le per-app split tunneling existe seulement sur Android.

### Windscribe, CyberGhost, TunnelBear — GUI only

Aucun support CLI sérieux pour le split tunneling par app. Configuration via la GUI dans les préférences de chaque app (_Split Tunneling_, _Smart Rules_, _SplitBear_ respectivement). TunnelBear et CyberGhost n'ont pas d'app Linux du tout.

### WireGuard pur — manuel

WireGuard ne connaît pas la notion d'app, seulement de routes. Sur Linux, deux approches :

**Approche 1 — restreindre `AllowedIPs`** : si tu n'as besoin du VPN que pour quelques sous-réseaux, retire `0.0.0.0/0` de ton conf et liste explicitement ce que tu veux tunneliser. Tout le reste (dont Groq) passe en clair.

**Approche 2 — exclusion par marquage** : laisse `AllowedIPs = 0.0.0.0/0` et ajoute dans la conf :

```ini
[Interface]
PostUp = ip rule add not fwmark 0xca6c table main priority 10
PostDown = ip rule del not fwmark 0xca6c table main priority 10
```

Puis lance dicton dans un cgroup qui marque le trafic, ou via `iptables -t mangle -A OUTPUT -m owner --uid-owner <uid> -j MARK --set-mark 0xca6c` (si dicton tourne sous un UID dédié).

C'est ad hoc — si tu n'es pas à l'aise avec `ip rule`, préfère un client managé (Mullvad, PIA).

### OpenVPN pur — manuel

Même esprit que WireGuard. Utiliser `--route-nopull` + routes statiques manuelles vers les sous-réseaux à tunneliser, ou règles `iptables`/`pf` côté firewall.

## Dernier recours : couper le VPN

Si rien de ce qui précède ne s'applique à ta config et que tu n'as pas envie de t'embêter : déconnecte simplement le VPN avant d'utiliser dicton. Le trafic dicton (audio vers Groq, transcription, cleanup) part en clair côté Groq de toute façon — le VPN ne t'apportait pas de garantie supplémentaire sur ce flux.

## Vérification rapide

Pour confirmer que ton split tunneling fonctionne, depuis dicton activé :

```bash
curl -sS -o /dev/null -w "%{http_code} via %{remote_ip}\n" \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  https://api.groq.com/openai/v1/models
```

Attendu : `200 via <IP non-VPN>`. Si c'est `403` ou que `remote_ip` correspond à ton point de sortie VPN, le split n'est pas pris en compte pour ce shell.
