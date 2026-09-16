import io
import zipfile
import uuid
import pytest
from flask_jwt_extended import create_access_token
from app import db
from app.infrastructure.database.models.models import User, Organization, Project, ProjectWorkflow, Role


class TestProjectDocumentsZip:

    def test_zip_unauthorized(self, client):
        res = client.get("/api/projects/1/documents/zip")
        assert res.status_code == 401
        res_post = client.post("/api/projects/1/documents/zip", json={"documents": []})
        assert res_post.status_code == 401

    def test_zip_project_not_found(self, client, app):
        with app.app_context():
            user = User.query.first()
            token = create_access_token(identity=str(user.id), additional_claims={"session_id": str(uuid.uuid4())})
            res = client.get(
                "/api/projects/9999999/documents/zip",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert res.status_code == 404
            assert "Project not found" in res.get_json()["msg"]

    def test_zip_empty_project_documents(self, client, app):
        with app.app_context():
            user = User.query.filter(User.org_id.isnot(None)).first() or User.query.first()
            org = Organization.query.first()
            org_id = user.org_id or (org.id if org else 1)
            token = create_access_token(identity=str(user.id), additional_claims={"session_id": str(uuid.uuid4())})

            # Create a project with no workflows
            proj = Project(
                org_id=org_id,
                project_uid=f"PRJ-EMPTY-{uuid.uuid4().hex[:6].upper()}",
                title="Empty Project for Zip Test",
                creator_id=user.id,
                status="In Progress"
            )
            db.session.add(proj)
            db.session.commit()
            pid = proj.id

            res = client.get(
                f"/api/projects/{pid}/documents/zip",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert res.status_code == 404
            assert "No documents found" in res.get_json()["msg"]

    def test_zip_download_with_post_payload(self, client, app, tmp_path):
        with app.app_context():
            user = User.query.filter(User.org_id.isnot(None)).first() or User.query.first()
            org = Organization.query.first()
            org_id = user.org_id or (org.id if org else 1)
            token = create_access_token(identity=str(user.id), additional_claims={"session_id": str(uuid.uuid4())})

            proj_uid = f"PRJ-ZIP-{uuid.uuid4().hex[:6].upper()}"
            proj_title = "Zip Payload Project"
            proj = Project(
                org_id=org_id,
                project_uid=proj_uid,
                title=proj_title,
                creator_id=user.id,
                status="In Progress"
            )
            db.session.add(proj)
            db.session.commit()
            pid = proj.id

            # Create a real test file in uploads directory or storage
            from app.infrastructure.storage.storage_service import storage
            test_content = b"Problem flow analysis chart binary data"
            saved = storage.save_file(
                io.BytesIO(test_content),
                filename="process_flow.png",
                subfolder="project_evidence"
            )
            file_url = saved.get("url")

            doc_payload = [
                {
                    "stage": 2,
                    "stageName": "Stage 2: Define Problem & Observation",
                    "title": "Process Flow Diagram",
                    "url": file_url,
                    "category": "Flow Diagram",
                    "ext": "PNG"
                },
                {
                    "stage": 8,
                    "stageName": "Stage 8: SOP Standardization & Closure",
                    "title": "Standard Operating Procedure Document",
                    "url": "https://example.com/external-sop-guide",
                    "category": "SOP Guide",
                    "ext": "DOC"
                }
            ]

            res = client.post(
                f"/api/projects/{pid}/documents/zip",
                headers={"Authorization": f"Bearer {token}"},
                json={"documents": doc_payload}
            )
            assert res.status_code == 200
            assert res.headers.get("Content-Type") == "application/zip"
            assert "attachment" in res.headers.get("Content-Disposition", "")
            assert f"{proj_uid}_Documents.zip" in res.headers.get("Content-Disposition", "")

            # Verify ZIP contents
            zip_bytes = io.BytesIO(res.data)
            with zipfile.ZipFile(zip_bytes, "r") as zf:
                namelist = zf.namelist()
                assert any("Stage 2" in name and "Process Flow Diagram.png" in name for name in namelist)
                assert any("Stage 8" in name and "Link.txt" in name for name in namelist)
                assert "README_Project_Documents_Index.txt" in namelist

                # Verify actual binary contents of the saved file inside the ZIP
                flow_entry = [n for n in namelist if "Process Flow Diagram.png" in n][0]
                with zf.open(flow_entry) as f:
                    assert f.read() == test_content

                # Verify README index
                with zf.open("README_Project_Documents_Index.txt") as f:
                    readme_content = f.read().decode("utf-8")
                    assert proj_uid in readme_content
                    assert proj_title in readme_content

    def test_zip_download_extracted_from_db_workflows(self, client, app):
        with app.app_context():
            user = User.query.filter(User.org_id.isnot(None)).first() or User.query.first()
            org = Organization.query.first()
            org_id = user.org_id or (org.id if org else 1)
            token = create_access_token(identity=str(user.id), additional_claims={"session_id": str(uuid.uuid4())})

            proj = Project(
                org_id=org_id,
                project_uid=f"PRJ-DBZIP-{uuid.uuid4().hex[:6].upper()}",
                title="Database Extracted Zip Project",
                creator_id=user.id,
                status="In Progress"
            )
            db.session.add(proj)
            db.session.flush()

            # Save real file via storage
            from app.infrastructure.storage.storage_service import storage
            test_content = b"Gemba Walk observation image data"
            saved = storage.save_file(
                io.BytesIO(test_content),
                filename="gemba_evidence.jpg",
                subfolder="project_evidence"
            )

            # Create workflow data with file references
            wf2 = ProjectWorkflow(
                project_id=proj.id,
                org_id=org_id,
                stage_id=2,
                data={
                    "process_observation": {
                        "gemba_evidence": saved.get("url")
                    },
                    "current_state": {
                        "media_files": [
                            {"name": "Defect Sample Photo", "url": saved.get("url")}
                        ]
                    }
                }
            )
            wf8 = ProjectWorkflow(
                project_id=proj.id,
                org_id=org_id,
                stage_id=8,
                data={
                    "sop": {
                        "attachment_url": "/uploads/sop/sop_final_guideline.pdf"
                    }
                }
            )
            db.session.add(wf2)
            db.session.add(wf8)
            db.session.commit()
            pid = proj.id

            # GET without body should extract from database
            res = client.get(
                f"/api/projects/{pid}/documents/zip",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert res.status_code == 200
            assert res.headers.get("Content-Type") == "application/zip"

            zip_bytes = io.BytesIO(res.data)
            with zipfile.ZipFile(zip_bytes, "r") as zf:
                namelist = zf.namelist()
                assert len(namelist) >= 3  # Gemba evidence, defect photo, sop link, and README
                assert any("Stage 2" in n for n in namelist)
                assert any("Stage 8" in n for n in namelist)
                assert "README_Project_Documents_Index.txt" in namelist

    def test_zip_cross_tenant_isolation(self, client, app):
        with app.app_context():
            # Create second organization with unique email
            org_uid = uuid.uuid4().hex[:8]
            org2 = Organization(name=f"Other Tenant Org {org_uid}", email=f"other_org_{org_uid}@example.com")
            db.session.add(org2)
            db.session.flush()

            other_user = User(
                org_id=org2.id,
                username=f"tenant_user_{uuid.uuid4().hex[:6]}",
                email=f"tenant_{uuid.uuid4().hex[:6]}@other.com",
                hashed_password="fakehash"
            )
            role_user = Role.query.filter_by(name="Team Member").first()
            if role_user:
                other_user.role_id = role_user.id
            db.session.add(other_user)

            # Create project belonging to org 1
            user1 = User.query.filter(User.org_id.isnot(None)).first() or User.query.first()
            org1 = Organization.query.first()
            org1_id = user1.org_id or (org1.id if org1 else 1)
            proj = Project(
                org_id=org1_id,
                project_uid=f"PRJ-TENANT-{uuid.uuid4().hex[:6].upper()}",
                title="Tenant Isolation Project",
                creator_id=user1.id,
                status="In Progress"
            )
            db.session.add(proj)
            db.session.commit()
            proj_id = proj.id

            # Generate token for other_user (different org)
            token = create_access_token(identity=str(other_user.id), additional_claims={"session_id": str(uuid.uuid4())})
            res = client.get(
                f"/api/projects/{proj_id}/documents/zip",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert res.status_code == 404
            assert "Project not found" in res.get_json()["msg"]
