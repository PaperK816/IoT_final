import json
import threading
import os
import sys
import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 将项目根目录加入环境变量，以便顺利导入 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

app = FastAPI(title="Personalized Space IoT Server", version="1.0.0")

# 配置 CORS 允许跨域请求，方便前端网页直接调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内存缓存：用于保存当前物联网设备上报的最新状态
latest_space_data = {
    "device_id": "waiting_for_device...",
    "timestamp": 0,
    "active_mode": "Normal",
    "current_user": "Yuanming",
    "states": {
        "light_power": "ON",
        "brightness": 80,
        "color_temp": 4000,
        "ac_power": "ON",
        "target_temp": 26.0,
        "ac_mode": "Auto",
        "music_status": "PAUSED",
        "volume": 40,
        "genre": "Standard",
        "indoor_temp": 25.5,
        "indoor_humidity": 50.0,
        "ambient_light": 300.0
    }
}

# ----------------- MQTT 后台客户端配置 -----------------
mqtt_client_id = f"{config.CLIENT_ID}_server_{os.getpid()}"
mqtt_client = mqtt.Client(client_id=mqtt_client_id)

if config.USERNAME and config.PASSWORD:
    mqtt_client.username_pw_set(config.USERNAME, config.PASSWORD)

if os.path.exists(config.CA_CERTS):
    mqtt_client.tls_set(ca_certs=config.CA_CERTS)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[Server MQTT] 后端成功连接到云端 MQTT 代理! (rc={rc})")
        # 订阅设备上报的遥测主题
        client.subscribe(config.TOPIC_TELEMETRY)
        print(f"[Server MQTT] 已订阅遥测主题: {config.TOPIC_TELEMETRY}")
    else:
        print(f"[Server MQTT] 连接失败，返回码: {rc}")


def on_message(client, userdata, msg):
    global latest_space_data
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        # 更新内存缓存
        latest_space_data = data
        # print(f"[Server MQTT] 收到遥测数据更新: 模式 -> {data.get('active_mode')}")
    except Exception as e:
        print(f"[Server MQTT] 解析上报数据出错: {e}")


mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


def start_mqtt_background_loop():
    """在独立线程中启动 MQTT 循环，保证不阻塞 FastAPI 异步服务"""
    try:
        print(f"[Server MQTT] 正在连接代理 {config.BROKER_HOST}:{config.BROKER_PORT}...")
        mqtt_client.connect(config.BROKER_HOST, config.BROKER_PORT, keepalive=60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[Server MQTT] 启动后台 MQTT 线程失败: {e}")


@app.on_event("startup")
def startup_event():
    # 启动时开启后台 MQTT 监听线程
    threading.Thread(target=start_mqtt_background_loop, daemon=True).start()


# ----------------- FastAPI RESTful API 定义 -----------------

class ControlCommand(BaseModel):
    action: str
    value: str


@app.get("/api/space/latest")
def get_latest_data():
    """提供给前端网页轮询的接口：获取当前个性化空间的最新状态"""
    return {
        "status": "success",
        "data": latest_space_data
    }


@app.post("/api/control")
def send_control_command(cmd: ControlCommand):
    """前端调用此接口下发控制指令，后端将其通过 MQTT 发布至云端"""
    try:
        payload = json.dumps({
            "action": cmd.action,
            "value": cmd.value
        })
        # 发布到控制主题
        info = mqtt_client.publish(config.TOPIC_COMMAND, payload, qos=1)
        info.wait_for_publish()

        print(f"==> [API Control] 成功下发控制指令: action={cmd.action}, value={cmd.value}")
        return {
            "status": "success",
            "message": f"Command {cmd.action} sent successfully",
            "sent_payload": {"action": cmd.action, "value": cmd.value}
        }
    except Exception as e:
        print(f"==> [API Control] 下发指令失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    # 启动 FastAPI 服务，端口设为 8000
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)