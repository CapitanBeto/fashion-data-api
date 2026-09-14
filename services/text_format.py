"""
Transforma los perfiles normalizados (salida de miapp.normalize_profile) al
formato de texto plano que se guarda en Google Drive.
"""


def _fmt(value, *, fallback="no disponible") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _fmt_hashtags(hashtags) -> str:
    if not hashtags:
        return ""
    return ", ".join(str(h) for h in hashtags)


def _fmt_caption(caption) -> str:
    if not caption or not str(caption).strip():
        return "sin caption"
    return str(caption)


def profile_to_block(profile: dict) -> str:
    """Convierte un único perfil (dict) en el bloque de texto USUARIO/POST."""
    lines = [
        f"USUARIO: {profile.get('account', '')}",
        f"SEGUIDORES: {_fmt(profile.get('followers'))}",
        f"SIGUIENDO: {_fmt(profile.get('following'))}",
        f"VERIFICADO: {'si' if profile.get('is_verified') else 'no'}",
    ]

    for post in profile.get("posts", []):
        lines.append("")
        lines.append("POST:")
        lines.append(f"Fecha: {_fmt(post.get('date_posted'))}")
        lines.append(f"Likes: {_fmt(post.get('likes'))}")
        lines.append(f"Comentarios: {_fmt(post.get('comments'))}")
        lines.append(f"URL: {_fmt(post.get('url'))}")
        lines.append(f"Hashtags: {_fmt_hashtags(post.get('hashtags'))}")
        lines.append(f"Caption: {_fmt_caption(post.get('caption'))}")

    return "\n".join(lines)


def profiles_to_blocks(profiles: list[dict]) -> dict[str, str]:
    """
    Convierte una lista de perfiles en un dict {username: bloque_de_texto},
    listo para hacer upsert en el archivo de Drive.
    """
    blocks = {}
    for profile in profiles:
        if not profile:
            continue
        account = profile.get("account")
        if not account:
            continue
        blocks[account] = profile_to_block(profile)
    return blocks