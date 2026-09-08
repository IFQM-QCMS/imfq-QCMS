from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.infrastructure.database.models.models import db, User, Plant, Department, AuditLog
from app.presentation.routes.admin_routes import admin_required, log_action
from datetime import datetime, timezone
from app.presentation.routes.error_helpers import internal_server_error

plant_bp = Blueprint('plant_bp', __name__)

def get_current_user():
    try:
        uid = get_jwt_identity()
        if isinstance(uid, dict):
            uid = uid.get('id')
        if uid and str(uid).isdigit():
            uid = int(uid)
        return db.session.get(User, uid)
    except Exception:
        return None

@plant_bp.route('', methods=['GET'])
@plant_bp.route('/', methods=['GET'])
@jwt_required()
def get_plants():
    """List all plant locations for the current user's organization."""
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"status": "error", "message": "User context not found"}), 404

        from app.infrastructure.database.models.models import Project, ProjectMember
        plants = Plant.query.filter_by(org_id=current_user.org_id).order_by(Plant.name).all()
        all_org_users = User.query.filter_by(org_id=current_user.org_id).all()
        all_depts = Department.query.filter_by(org_id=current_user.org_id).all()

        # Collect distinct user IDs participating in QC projects
        projects = Project.query.filter_by(org_id=current_user.org_id).all()
        project_ids = [pr.id for pr in projects]
        qc_user_ids = set()
        for pr in projects:
            if pr.creator_id: qc_user_ids.add(pr.creator_id)
            if pr.team_leader_id: qc_user_ids.add(pr.team_leader_id)
            if pr.facilitator_id: qc_user_ids.add(pr.facilitator_id)
            if pr.reviewer_id: qc_user_ids.add(pr.reviewer_id)

        if project_ids:
            members = ProjectMember.query.filter(ProjectMember.project_id.in_(project_ids)).all()
            for m in members:
                qc_user_ids.add(m.user_id)

        total_org_qc_users = len([u for u in all_org_users if u.id in qc_user_ids])
        
        result = []
        for p in plants:
            p_depts = [d for d in all_depts if d.plant_id == p.id]
            p_users = [u for u in all_org_users if u.plant_id == p.id]
            p_qc_users = [u for u in p_users if u.id in qc_user_ids]
            result.append({
                "id": p.id,
                "org_id": p.org_id,
                "name": p.name,
                "code": p.code or "",
                "location": p.location or "",
                "created_at": p.created_at.strftime('%Y-%m-%d %H:%M:%S') if p.created_at else "",
                "department_count": len(p_depts),
                "user_count": len(p_users),
                "employee_count": len(p_users),
                "qc_user_count": len(p_qc_users),
                "qc_employee_count": len(p_qc_users)
            })
            
        return jsonify({
            "status": "success", 
            "plants": result,
            "total_employees": len(all_org_users),
            "total_qc_employees": total_org_qc_users
        }), 200
    except Exception as e:
        db.session.rollback()
        return internal_server_error(e, "An internal server error occurred.")

@plant_bp.route('', methods=['POST'])
@plant_bp.route('/', methods=['POST'])
@jwt_required()
@admin_required
def create_plant():
    """Create a new plant location."""
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"status": "error", "message": "User context not found"}), 404

        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        code = (data.get('code') or '').strip()
        location = (data.get('location') or '').strip()

        if not name:
            return jsonify({"status": "error", "message": "Plant location name is required"}), 400

        # Check SaaS Subscription Plan Location Limit
        from app.domain.services.subscription_service import SubscriptionManager
        can_add, limit_msg = SubscriptionManager.check_location_limit(current_user.org_id)
        if not can_add:
            return jsonify({
                "status": "error",
                "message": limit_msg,
                "error_code": "LOCATION_LIMIT_REACHED"
            }), 403

        # Case-insensitive duplicate name check within the same organisation
        from sqlalchemy import func as sqlfunc
        existing = Plant.query.filter(
            Plant.org_id == current_user.org_id,
            sqlfunc.lower(Plant.name) == name.lower()
        ).first()
        if existing:
            return jsonify({
                "status": "error",
                "message": f"A plant location named '{existing.name}' already exists in your organisation. "
                           "Plant names must be unique (case-insensitive)."
            }), 409

        new_plant = Plant(
            org_id=current_user.org_id,
            name=name,
            code=code,
            location=location,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        db.session.add(new_plant)
        db.session.commit()

        log_action(current_user.id, "CREATE_PLANT", current_user.org_id, "plants", new_plant.id, {"name": name, "code": code})

        return jsonify({
            "status": "success",
            "message": "Plant location created successfully",
            "plant": {
                "id": new_plant.id,
                "name": new_plant.name,
                "code": new_plant.code,
                "location": new_plant.location
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return internal_server_error(e, "An internal server error occurred.")

@plant_bp.route('/<int:plant_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_plant(plant_id):
    """Update a plant location."""
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"status": "error", "message": "User context not found"}), 404

        plant = Plant.query.filter_by(id=plant_id, org_id=current_user.org_id).first()
        if not plant:
            return jsonify({"status": "error", "message": "Plant location not found"}), 404

        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        code = (data.get('code') or '').strip()
        location = (data.get('location') or '').strip()

        if name:
            from sqlalchemy import func as sqlfunc
            dup = Plant.query.filter(
                Plant.org_id == current_user.org_id,
                sqlfunc.lower(Plant.name) == name.lower(),
                Plant.id != plant_id
            ).first()
            if dup:
                return jsonify({
                    "status": "error",
                    "message": f"A plant location named '{dup.name}' already exists in your organisation. "
                               "Plant names must be unique (case-insensitive)."
                }), 409
            plant.name = name

        if 'code' in data:
            plant.code = code
        if 'location' in data:
            plant.location = location

        db.session.commit()

        log_action(current_user.id, "UPDATE_PLANT", current_user.org_id, "plants", plant.id, data)

        return jsonify({
            "status": "success",
            "message": "Plant location updated successfully",
            "plant": {
                "id": plant.id,
                "name": plant.name,
                "code": plant.code,
                "location": plant.location
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        return internal_server_error(e, "An internal server error occurred.")


@plant_bp.route('/<int:plant_id>/stats', methods=['GET'])
@jwt_required()
@admin_required
def get_plant_stats(plant_id):
    """Return dept + user counts for the deletion confirmation dialog."""
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"status": "error", "message": "User context not found"}), 404
        plant = Plant.query.filter_by(id=plant_id, org_id=current_user.org_id).first()
        if not plant:
            return jsonify({"status": "error", "message": "Plant not found"}), 404
        dept_count = Department.query.filter_by(plant_id=plant_id, org_id=current_user.org_id).count()
        user_count = User.query.filter_by(plant_id=plant_id, org_id=current_user.org_id).count()
        return jsonify({
            "status": "success",
            "plant_id": plant_id,
            "plant_name": plant.name,
            "dept_count": dept_count,
            "user_count": user_count
        }), 200
    except Exception as e:
        return internal_server_error(e, "An internal server error occurred.")


@plant_bp.route('/<int:plant_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_plant(plant_id):
    """
    Smart plant delete.
    Body JSON params:
      action          : 'delete_all' | 'move_to_plant' | 'new_plant'
      target_plant_id : (required for move_to_plant) existing plant id
      new_plant_name  : (required for new_plant) name for the new plant
      new_plant_code  : (optional for new_plant) code for the new plant
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"status": "error", "message": "User context not found"}), 404

        plant = Plant.query.filter_by(id=plant_id, org_id=current_user.org_id).first()
        if not plant:
            return jsonify({"status": "error", "message": "Plant location not found"}), 404

        data   = request.get_json(silent=True) or {}
        action = data.get('action', '').strip()

        departments = Department.query.filter_by(plant_id=plant_id, org_id=current_user.org_id).all()
        users       = User.query.filter_by(plant_id=plant_id, org_id=current_user.org_id).all()

        if not action:
            if departments or users:
                return jsonify({
                    "status": "error",
                    "message": f"This plant has {len(departments)} department(s) and {len(users)} user(s). "
                               "Please choose what to do with them before deleting."
                }), 400
            db.session.execute(db.text("UPDATE departments SET plant_id = NULL WHERE plant_id = :p_id"), {"p_id": plant_id})
            db.session.execute(db.text("UPDATE users SET plant_id = NULL WHERE plant_id = :p_id"), {"p_id": plant_id})
            db.session.commit()
            db.session.expire_all()
            Plant.query.filter_by(id=plant_id).delete(synchronize_session=False)
            db.session.commit()

        elif action == 'delete_all':
            from app.presentation.routes.admin_routes import batch_disassociate_and_delete_users
            try:
                db.session.execute(db.text("ALTER TABLE audit_logs ALTER COLUMN user_id DROP NOT NULL;"))
                db.session.commit()
            except Exception:
                db.session.rollback()

            all_users_to_delete = list(users)
            user_ids_seen = set(u.id for u in users)

            for d in departments:
                dept_users = User.query.filter_by(department_id=d.id, org_id=current_user.org_id).all()
                for du in dept_users:
                    if du.id not in user_ids_seen:
                        all_users_to_delete.append(du)
                        user_ids_seen.add(du.id)

            batch_disassociate_and_delete_users(all_users_to_delete, admin_user_id=current_user.id)

            for d in departments:
                db.session.execute(db.text("UPDATE projects SET department_id = NULL WHERE department_id = :d_id"), {"d_id": d.id})
                db.session.execute(db.text("UPDATE sop_master SET department_id = NULL WHERE department_id = :d_id"), {"d_id": d.id})
                db.session.execute(db.text("UPDATE knowledge_repository SET department_id = NULL WHERE department_id = :d_id"), {"d_id": d.id})
            db.session.commit()
            db.session.expire_all()

            Department.query.filter_by(plant_id=plant_id, org_id=current_user.org_id).delete(synchronize_session=False)
            db.session.commit()
            db.session.expire_all()

            Plant.query.filter_by(id=plant_id).delete(synchronize_session=False)
            db.session.commit()

        elif action == 'move_to_plant':
            target_id = data.get('target_plant_id')
            if not target_id:
                return jsonify({"status": "error", "message": "'target_plant_id' is required."}), 400
            target_id = int(target_id)
            if target_id == plant_id:
                return jsonify({"status": "error", "message": "Cannot move items to the plant location being deleted."}), 400
            target_plant = Plant.query.filter_by(id=target_id, org_id=current_user.org_id).first()
            if not target_plant:
                return jsonify({"status": "error", "message": "Target plant not found."}), 404

            # Handle department relocation/merging carefully to avoid uq_departments_plant_name violation
            target_depts = Department.query.filter_by(plant_id=target_plant.id, org_id=current_user.org_id).all()
            target_depts_by_name = {d.name.strip().lower(): d for d in target_depts}

            for d in departments:
                d_name_key = d.name.strip().lower()
                if d_name_key in target_depts_by_name:
                    # MERGE: Target plant already has a department with this name!
                    matching_target_dept = target_depts_by_name[d_name_key]
                    # Move users from old dept to matching target dept
                    db.session.execute(
                        db.text("UPDATE users SET department_id = :new_dept, plant_id = :new_plant WHERE department_id = :old_dept AND org_id = :org_id"),
                        {"new_dept": matching_target_dept.id, "new_plant": target_plant.id, "old_dept": d.id, "org_id": current_user.org_id}
                    )
                    # Move projects from old dept to matching target dept
                    db.session.execute(
                        db.text("UPDATE projects SET department_id = :new_dept WHERE department_id = :old_dept AND org_id = :org_id"),
                        {"new_dept": matching_target_dept.id, "old_dept": d.id, "org_id": current_user.org_id}
                    )
                    # Move SOPs and knowledge repository
                    db.session.execute(
                        db.text("UPDATE sop_master SET department_id = :new_dept WHERE department_id = :old_dept"),
                        {"new_dept": matching_target_dept.id, "old_dept": d.id}
                    )
                    db.session.execute(
                        db.text("UPDATE knowledge_repository SET department_id = :new_dept WHERE department_id = :old_dept"),
                        {"new_dept": matching_target_dept.id, "old_dept": d.id}
                    )
                    db.session.commit()
                    db.session.expire_all()
                    # Delete the duplicate department in old plant
                    Department.query.filter_by(id=d.id).delete(synchronize_session=False)
                    db.session.commit()
                else:
                    # MOVE: No name clash, reassign this department to target plant
                    db.session.execute(
                        db.text("UPDATE departments SET plant_id = :new_plant WHERE id = :old_dept AND org_id = :org_id"),
                        {"new_plant": target_plant.id, "old_dept": d.id, "org_id": current_user.org_id}
                    )
                    db.session.execute(
                        db.text("UPDATE users SET plant_id = :new_plant WHERE department_id = :old_dept AND org_id = :org_id"),
                        {"new_plant": target_plant.id, "old_dept": d.id, "org_id": current_user.org_id}
                    )

            # Move users directly attached to old_plant
            db.session.execute(
                db.text("UPDATE users SET plant_id = :new_plant WHERE plant_id = :old_plant AND org_id = :org_id"),
                {"new_plant": target_plant.id, "old_plant": plant_id, "org_id": current_user.org_id}
            )

            # Update projects with string plant name
            db.session.execute(
                db.text("UPDATE projects SET plant = :new_name WHERE plant = :old_name AND org_id = :org_id"),
                {"new_name": target_plant.name, "old_name": plant.name, "org_id": current_user.org_id}
            )
            db.session.commit()
            db.session.expire_all()

            Plant.query.filter_by(id=plant_id).delete(synchronize_session=False)
            db.session.commit()

        elif action == 'new_plant':
            new_name = (data.get('new_plant_name') or '').strip()
            if not new_name:
                return jsonify({"status": "error", "message": "'new_plant_name' is required."}), 400
            from sqlalchemy import func as sqlfunc
            clash = Plant.query.filter(
                Plant.org_id == current_user.org_id,
                sqlfunc.lower(Plant.name) == new_name.lower()
            ).first()
            if clash:
                return jsonify({"status": "error",
                                "message": f"A plant named '{clash.name}' already exists."}), 409
            new_plant = Plant(
                org_id=current_user.org_id,
                name=new_name,
                code=(data.get('new_plant_code') or '').strip(),
                created_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            db.session.add(new_plant)
            db.session.commit()

            # For new plant: reassign all departments and users
            for d in departments:
                db.session.execute(
                    db.text("UPDATE departments SET plant_id = :new_plant WHERE id = :old_dept AND org_id = :org_id"),
                    {"new_plant": new_plant.id, "old_dept": d.id, "org_id": current_user.org_id}
                )
                db.session.execute(
                    db.text("UPDATE users SET plant_id = :new_plant WHERE department_id = :old_dept AND org_id = :org_id"),
                    {"new_plant": new_plant.id, "old_dept": d.id, "org_id": current_user.org_id}
                )

            # Reassign users whose plant_id is old_plant to new plant
            db.session.execute(
                db.text("UPDATE users SET plant_id = :new_plant WHERE plant_id = :old_plant AND org_id = :org_id"),
                {"new_plant": new_plant.id, "old_plant": plant_id, "org_id": current_user.org_id}
            )

            # Update projects with string plant name
            db.session.execute(
                db.text("UPDATE projects SET plant = :new_name WHERE plant = :old_name AND org_id = :org_id"),
                {"new_name": new_plant.name, "old_name": plant.name, "org_id": current_user.org_id}
            )
            db.session.commit()
            db.session.expire_all()

            Plant.query.filter_by(id=plant_id).delete(synchronize_session=False)
            db.session.commit()
        else:
            return jsonify({"status": "error", "message": f"Unknown action '{action}'."}), 400

        log_action(current_user.id, "DELETE_PLANT", current_user.org_id, "plants", plant_id,
                   {"action": action, "depts_affected": len(departments), "users_affected": len(users)})

        return jsonify({"status": "success", "message": "Plant location deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return internal_server_error(e, "An internal server error occurred.")
