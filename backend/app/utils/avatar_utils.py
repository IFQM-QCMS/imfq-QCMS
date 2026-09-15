import os
import tempfile
from flask import current_app

def get_profile_picture_url(user_or_path):
    if not user_or_path:
        return "/api/auth/avatar/User"
    
    if isinstance(user_or_path, str):
        path = user_or_path
        username = 'User'
    else:
        path = getattr(user_or_path, 'profile_picture', None)
        username = getattr(user_or_path, 'username', 'User') or 'User'

    if not path:
        return f"/api/auth/avatar/{username}"
        
    if path.startswith('http://') or path.startswith('https://') or path.startswith('data:'):
        return path

    # Strip any prepended /uploads/ or uploads/ to get clean filename
    if path.startswith('/uploads/'):
        clean_name = path[len('/uploads/'):]
    elif path.startswith('uploads/'):
        clean_name = path[len('uploads/'):]
    else:
        clean_name = path

    clean_name = clean_name.replace('\\', '/').lstrip('/')

    # If remote storage is active (Supabase or Azure), local filesystem won't have the file
    try:
        from app.infrastructure.storage import storage
        if storage and storage.backend in ('supabase', 'azure'):
            return f"/uploads/{clean_name}"
    except Exception:
        pass

    upload_folder = current_app.config.get('UPLOAD_FOLDER') if current_app else None
    fallback_tmp_dir = os.path.join(tempfile.gettempdir(), 'qcms_uploads')
    alt_tmp_dir = '/tmp/uploads'
    frontend_uploads = os.path.abspath(os.path.join(current_app.root_path, '..', '..', 'frontend', 'uploads')) if current_app else None
    search_dirs = [d for d in (upload_folder, fallback_tmp_dir, alt_tmp_dir, frontend_uploads) if d and os.path.isdir(d)]

    base_name = os.path.basename(clean_name)
    candidates = [
        clean_name,
        base_name,
        f"avatars/{base_name}",
        f"branding/{base_name}"
    ]

    from app.utils.security_utils import safe_resolve_path
    for s_dir in search_dirs:
        for cand in candidates:
            safe_cand = safe_resolve_path(s_dir, cand)
            if safe_cand and os.path.isfile(safe_cand):
                return f"/uploads/{clean_name}"

    # If the user has a saved avatar path (starts with avatar_ or in avatars/),
    # return the /uploads/ path so the backend /uploads/<filename> route can serve it
    if clean_name and ('avatar_' in clean_name or 'avatars/' in clean_name):
        return f"/uploads/{clean_name}"

    return f"/api/auth/avatar/{username}"
