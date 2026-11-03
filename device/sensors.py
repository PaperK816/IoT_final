import json
import time
import random
import os
import sys
import paho.mqtt.client as mqtt

# 将项目根目录加入环境变量，以便顺利导入 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class PersonalizedSpaceDevice:
    def __init__(self, device_id='space_assistant_01'):
        self.device_id = device_id
        self.client_id = f'{config.CLIENT_ID}_{random.randint(1000, 9999)}'
        self.client = mqtt.Client(client_id=self.client_id)

        if config.USERNAME and config.PASSWORD:
            self.client.username_pw_set(config.USERNAME, config.PASSWORD)

        if os.path.exists(config.CA_CERTS):
            self.client.tls_set(ca_certs=config.CA_CERTS)

        self.client.on_connect = self.on_connect
        self.client.on_publish = self.on_publish
        self.client.on_message = self.on_message

        # 初始空间状态与用户偏好设定
        self.active_mode = "Normal (标准模式)"
        self.current_user = "Yuanming (主人)"

        # 空间内智能设备的初始状态字典
        self.state = {
            "light_power": "ON",
            "brightness": 80,  # 照明亮度 (%)
            "color_temp": 4000,  # 色温 (K)，从暖光到冷光

            "ac_power": "ON",
            "target_temp": 26.0,  # 空调设定温度 (℃)
            "ac_mode": "Auto",  # 空调模式: Cool, Heat, Auto

            "music_status": "PAUSED",
            "volume": 40,  # 音量 (%)
            "genre": "Light Piano",  # 当前播放音乐风格

            # 环境感知数据
            "indoor_temp": 25.5,
            "indoor_humidity": 50.0,
            "ambient_light": 300.0
        }

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f'[SensorDevice] 智能空间助手设备连接 MQTT 代理成功! (rc={rc})')
            # 订阅控制主题，接收来自服务器端的模式切换指令
            client.subscribe(config.TOPIC_COMMAND)
            print(f'[SensorDevice] 已成功订阅控制主题: {config.TOPIC_COMMAND}')
        else:
            print(f'[SensorDevice] 连接失败，返回码 {rc}')

    def on_publish(self, client, userdata, mid):
        pass

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8')
            print(f'[SensorDevice] 收到来自 {msg.topic} 的控制指令: {payload}')
            data = json.loads(payload)

            # 核心智能响应逻辑：根据前端/服务器下发的模式指令联动调整设备
            action = data.get('action')
            if action == 'set_mode':
                mode = data.get('value', 'Normal')
                self.apply_mode_settings(mode)
            elif action == 'adjust_device':
                dev = data.get('target')
                val = data.get('value')
                print(f'==> [独立设备调节] 目标: {dev}, 数值: {val}')
        except Exception as e:
            print(f'[SensorDevice] 解析控制指令出错: {e}')

    def apply_mode_settings(self, mode):
        """根据不同的个性化偏好模式，自动调整照明、空调与音乐（系统智能响应）"""
        self.active_mode = mode
        if mode == 'Focus':
            self.state['brightness'] = 90
            self.state['color_temp'] = 5500  # 冷白光，提高专注度
            self.state['target_temp'] = 24.0
            self.state['music_status'] = 'PLAYING'
            self.state['genre'] = 'Lo-Fi Focus Beats'
            print('==> [策略执行] 已切换至【专注办公模式】：高亮度冷光，温度调至24℃。')
        elif mode == 'Cinema':
            self.state['brightness'] = 15
            self.state['color_temp'] = 2700  # 暖黄微光
            self.state['target_temp'] = 25.0
            self.state['music_status'] = 'PLAYING'
            self.state['genre'] = 'Cinematic Epic'
            print('==> [策略执行] 已切换至【影音观影模式】：低照度暖光，温度调至25℃。')
        elif mode == 'Leisure':
            self.state['brightness'] = 60
            self.state['color_temp'] = 3500  # 柔和自然光
            self.state['target_temp'] = 26.0
            self.state['music_status'] = 'PLAYING'
            self.state['genre'] = 'Jazz & Bossa Nova'
            print('==> [策略执行] 已切换至【轻松休闲模式】：柔和光照，温度调至26℃。')
        else:
            self.active_mode = 'Normal'
            self.state['brightness'] = 80
            self.state['color_temp'] = 4000
            self.state['target_temp'] = 26.0
            self.state['music_status'] = 'PAUSED'
            print('==> [策略执行] 已恢复【标准模式】。')

    def generate_telemetry_data(self):
        """模拟环境温度平滑向空调设定目标温度靠拢，并加入自然波动"""
        target_temp = self.state.get('target_temp', 26.0)
        current_temp = self.state['indoor_temp']

        # 让室内温度以一定速率平滑向目标设定温度逼近（模拟空调控温效果）
        new_temp = current_temp + (target_temp - current_temp) * 0.3 + random.uniform(-0.04, 0.04)
        self.state['indoor_temp'] = round(new_temp, 2)

        # 湿度也伴随轻微自然波动
        self.state['indoor_humidity'] = round(
            max(35.0, min(75.0, self.state['indoor_humidity'] + random.uniform(-0.3, 0.3))), 1
        )

        return {
            "device_id": self.device_id,
            "timestamp": int(time.time()),
            "active_mode": self.active_mode,
            "current_user": self.current_user,
            "states": self.state
        }

    def start(self):
        print(f'[SensorDevice] 正在连接至云端代理 {config.BROKER_HOST}:{config.BROKER_PORT}...')
        try:
            self.client.connect(config.BROKER_HOST, config.BROKER_PORT, keepalive=60)
            self.client.loop_start()

            print(f'[SensorDevice] 开始定时向主题 {config.TOPIC_TELEMETRY} 上报个性化空间状态...')

            while True:
                data = self.generate_telemetry_data()
                payload = json.dumps(data)
                self.client.publish(config.TOPIC_TELEMETRY, payload, qos=1)
                print(
                    f'[已上报状态] 模式: {data["active_mode"]} | 照明: {data["states"]["brightness"]}% | 室温: {data["states"]["indoor_temp"]}℃ (目标:{data["states"]["target_temp"]}℃)')
                time.sleep(5)
        except KeyboardInterrupt:
            print('[SensorDevice] 正在停止智能空间设备...')
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as e:
            print(f'[SensorDevice] 连接发生错误: {e}')


if __name__ == '__main__':
    sensor_device = PersonalizedSpaceDevice()
    sensor_device.start()