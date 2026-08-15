import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app
from app.database.session import SessionLocal
from app.features.users.user_models import User
from app.shared.enums import UserRole, DeviceKeyType
from app.features.devices.device_models import DeviceCredential
from app.core.security import get_password_hash, get_api_key_hash

def setup_test_data(db):
    users = {
        "maintainer": {"username": "fuzz_maintainer", "role": UserRole.MAINTAINER},
        "manager": {"username": "fuzz_manager", "role": UserRole.MANAGER},
        "employee": {"username": "fuzz_employee", "role": UserRole.EMPLOYEE},
    }
    
    for key, data in users.items():
        user = db.query(User).filter(User.username == data["username"]).first()
        if not user:
            user = User(
                username=data["username"],
                name=f"Fuzz {data['role'].value}",
                password_hash=get_password_hash("password123"),
                role=data["role"],
                is_active=True,
                email=f"{data['username']}@test.com"
            )
            db.add(user)
    
    device_key = "fuzz_device_api_key_123"
    consumer_key = "fuzz_consumer_api_key_123"
    
    for name, k, kt in [("fuzz_device", device_key, DeviceKeyType.DEVICE), 
                        ("fuzz_consumer", consumer_key, DeviceKeyType.CONSUMER)]:
        cred = db.query(DeviceCredential).filter(DeviceCredential.name == name).first()
        if not cred:
            cred = DeviceCredential(
                name=name, api_key_hash=get_api_key_hash(k),
                key_type=kt, is_active=True
            )
            db.add(cred)
            
    db.commit()
    return device_key, consumer_key

def generate_report():
    db = SessionLocal()
    try:
        device_key, consumer_key = setup_test_data(db)
    finally:
        db.close()
        
    client = TestClient(app)
    
    tokens = {}
    for u in ["fuzz_maintainer", "fuzz_manager", "fuzz_employee"]:
        resp = client.post("/api/v1/auth/login", data={"username": u, "password": "password123"})
        if resp.status_code == 200:
            role = u.split('_')[1]
            tokens[role] = resp.json()["access_token"]

    auth_scenarios = {
        "No Auth": {},
        "Employee": {"Authorization": f"Bearer {tokens.get('employee', '')}"},
        "Manager": {"Authorization": f"Bearer {tokens.get('manager', '')}"},
        "Maintainer": {"Authorization": f"Bearer {tokens.get('maintainer', '')}"},
        "Device": {"X-API-KEY": device_key},
        "Consumer": {"X-CONSUMER-API-KEY": consumer_key}
    }
    
    openapi = client.get("/api/v1/openapi.json").json()
    paths = openapi.get("paths", {})
    
    report = ["# 🛡️ Fuzzing & Route Testing Report\n", "Validação total de rotas com base na especificação OpenAPI.\n"]
    
    for path, methods_dict in paths.items():
        if "/api/v1/backup/trigger" in path or "/api/v1/telegram/" in path:
            continue

        valid_path = path.replace("{id}", "1").replace("{user_id}", "1").replace("{sensor_index}", "1").replace("{record_id}", "1").replace("{version}", "1.0.0")
        invalid_path = path.replace("{id}", "invalid_str").replace("{user_id}", "invalid_str").replace("{sensor_index}", "abc").replace("{record_id}", "x").replace("{version}", "invalid")
        
        valid_path = re.sub(r'\{[^}]+\}', '1', valid_path)
        invalid_path = re.sub(r'\{[^}]+\}', 'invalid', invalid_path)
        
        for method_str, operation in methods_dict.items():
            method = method_str.upper()
            if method == "OPTIONS": continue
            
            report.append(f"\n## {method} {path}")
            print(f"Testing {method} {path}")
            
            payloads = [
                ("Valid/Empty Dict", {}),
                ("List instead of Dict", []),
                ("String instead of Dict", "Invalid String Payload"),
                ("Extremely Large Payload", {"data": "X" * 10000}),
            ]
            
            req_body = operation.get("requestBody", {})
            has_body = bool(req_body)
            
            for auth_name, headers in auth_scenarios.items():
                for p_name, payload in payloads:
                    if not has_body and p_name != "Valid/Empty Dict":
                        continue
                        
                    for path_variant, path_desc in [(valid_path, "Valid Path Params"), (invalid_path, "Invalid Path Params")]:
                        if path_desc == "Invalid Path Params" and path_variant == valid_path:
                            continue
                            
                        scenario_desc = f"{auth_name} | {p_name} | {path_desc}"
                        
                        try:
                            kwargs = {"headers": headers}
                            if has_body or method in ["POST", "PUT", "PATCH"]:
                                kwargs["json"] = payload
                                
                            response = client.request(method.upper(), path_variant, **kwargs)
                            
                            status = response.status_code
                            
                            if status >= 500:
                                marker = "❌ CRITICAL ERROR (500)"
                            elif status == 200 and path_desc == "Invalid Path Params" and path != valid_path:
                                marker = "⚠️ WARNING (Accepted Invalid Path Param)"
                            else:
                                marker = "✅ OK"
                                
                            report.append(f"- **{scenario_desc}**: HTTP {status} {marker}")
                            
                            if status >= 500:
                                report.append(f"  - *Details*: `{response.text[:300]}`")
                                
                        except Exception as e:
                            report.append(f"- **{scenario_desc}**: Exception `{str(e)}` ❌ FATAL CRASH")

    report_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "route_test_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
        
    print(f"Total validation complete! Report generated at {report_path}")


def test_placeholder():
    pass


if __name__ == "__main__":
    generate_report()
