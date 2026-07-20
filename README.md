
![GitHub Repo stars](https://img.shields.io/github/stars/c1pher-cn/heweather?style=for-the-badge&label=Stars&color=green)
![GitHub forks](https://img.shields.io/github/forks/c1pher-cn/heweather?style=for-the-badge&label=Forks&color=green)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/c1pher-cn/heweather?style=for-the-badge&color=green)
![GitHub release (latest by date)](https://img.shields.io/github/downloads/c1pher-cn/heweather/total?style=for-the-badge&color=green)
![GitHub release (latest by date)](https://img.shields.io/github/downloads/c1pher-cn/heweather/latest/total?style=for-the-badge&color=green)



# 和风天气 homeassistant插件

  
  如果觉得对你有帮助，就来b站支持一波吧：[_小愚_](https://space.bilibili.com/15856864)

## 配置说明：

1.使用和风官方最新api版本

2.必须申请开发者账号里的免费api，请务必升级到开发者账号（免费，api权限会比普通用户高一些）https://console.qweather.com/#/console

3.appkey申请需要先[创建项目](https://console.qweather.com/project?lang=zh),后选创建凭据，建议选择 JSON Web Token (JWT) ,公钥见第5步

4.在HACS商店中搜索heweather,找到本插件并下载

<img width="1671" height="299" alt="image" src="https://github.com/user-attachments/assets/45aa3754-4c9b-411e-b168-603835d58b9a" />

5.设置->设备与服务->添加集成->搜索heweather->选择本插件，同时建议使用JWT凭证，（API模式将在2027年废弃）。

<img width="581" height="350" alt="image" src="https://github.com/user-attachments/assets/2f7c4f00-894a-4bc1-8fab-6b295c57accc" />
<img width="667" height="417" alt="image" src="https://github.com/user-attachments/assets/66e1acbe-4e6f-490b-a797-ea2e9837b625" />
<img width="571" height="635" alt="image" src="https://github.com/user-attachments/assets/90d51643-0f42-4aec-8f7a-dd5179135413" />

  
  项目id点击已创建的项目后可见。
  
  凭据id在创建凭据后可见，创建JWT凭据时粘贴ha页面显示的公钥即可。
  
  <img width="1610" height="653" alt="image" src="https://github.com/user-attachments/assets/47748808-b52c-4980-b38d-df42a4b17277" />
  
  HOST地址见设置页面
  
  <img width="1086" height="345" alt="image" src="https://github.com/user-attachments/assets/5ab678ab-09d0-4a83-8635-9a32432606dd" />
  
  国内的城市区域location、经纬度关系：
  
  https://github.com/qwd/LocationList/blob/master/China-City-List-latest.csv


6. 灾害预警过滤：使用和风 API 字段 **`severity`**（严重程度），不是 `headline` / `description`，也不是 `color`。

   官方定义见：[预警信息 · 严重程度 severity](https://dev.qweather.com/docs/resource/warning-info/#severity)

   | `severity`（API 原文字段） | 官方含义 |
   |---|---|
   | `unknown` | 严重性未知 |
   | `minor` | 对生命或财产构成的威胁极小或没有已知威胁 |
   | `moderate` | 对生命或财产可能构成威胁 |
   | `severe` | 对生命或财产构成的重大威胁 |
   | `extreme` | 对生命或财产构成的严重威胁 |

   > 官方说明：严重等级可能按当地规范新增，代码应兼容未知取值；建议不要写死枚举做展示，但本集成做「最低关注等级」过滤时，会把已知取值映射成内部阈值再比较。

   **集成里的「预警级别」配置（`disasterlevel`，默认 `3`）**：你选的是**最低关注阈值**（数字越大越严）。命中条件为：

   `映射后的 severity 数值 ≥ disasterlevel`

   内部映射（便于阈值比较；含历史兼容与颜色别名）：

   | 阈值 | 主要对应的 `severity` / 别名 | 说明 |
   |---|---|---|
   | 0 | `unknown` / `none` / `cancel` / `white` | 未知或不参与告警 |
   | 1 | `standard`（兼容）/ `blue` | 官方 severity 表未列 standard，仅兼容 |
   | 2 | **`minor`** / `green` | 威胁极小 |
   | 3 | **`moderate`** / `yellow` | 可能构成威胁（默认） |
   | 4 | `major`（兼容）/ `orange` | 官方 severity 表未列 major，仅兼容 |
   | 5 | **`severe`** / `red` | 重大威胁 |
   | 6 | **`extreme`** / `black` | 严重威胁 |

   **预警内容（disastermsg）**：
   - `title`（仅标题）：只取每条的 `headline`，多条用中文分号 `；` 拼接。
   - `allmsg`（所有信息，默认）：**只取**每条的 `description`（不含 `headline`），多条用 `；` 拼接，例如：  
     `南京市气象台发布高温黄色预警，……；江苏省气象台发布高温橙色预警，……`


## 一小时天气预警

需要自己在template里配置一个sensor模板，可以参考我的配置（读取小时级天气预报，然后判断是否有雨雪天气，有的话sensor的状态会被置为on，同时sensor的states的值即为具体的天气信息和降水概率）

<code>
  template:
  - trigger:
      - platform: time_pattern
        hours: "*"
    action:
      - service: weather.get_forecasts
        target:
          entity_id: weather.he_feng_tian_qi
        data:
          type: hourly
        response_variable: forecast
    sensor:
      - name: heweather_rain_warn
        unique_id: heweather_rain_warn
        state: >
           {% if forecast['weather.he_feng_tian_qi'].forecast[0].condition in ('sunny','cloudy','partlycloudy','windy') %}
           off
           {% else %}
           on
           {% endif %}
        attributes:
          states: >
                   {% if forecast['weather.he_feng_tian_qi'].forecast[0].condition in ('sunny','cloudy','partlycloudy','windy') %}
                    未来一小时，天气{{ forecast['weather.he_feng_tian_qi'].forecast[0].text }}，没有降雨
                   {% else %}
                    接下来一小时会有{{ forecast['weather.he_feng_tian_qi'].forecast[0].text }}，降水概率为 {{ forecast['weather.he_feng_tian_qi'].forecast[0].precipitation_probability}}%
                   {% endif %}
</code>



## 自动化配置实例

https://www.bilibili.com/read/cv18078640


## v2.5 实体与自动化（推荐）

本集成已将常用数据拆成可直接在自动化中引用的 **sensor / binary_sensor**，无需再手写 template 读小时预报。

### 内置 binary_sensor（适合自动化触发）

| 实体（名称） | 说明 | 状态 |
|---|---|---|
| 灾害预警(开关) | 达到你配置的灾害等级时为 on | `on` / `off`，详情在属性 `states` |
| 一小时降水预警 | 下一小时预报为雨雪类天气时为 on | `on` / `off`，属性含降水概率 |
| 分钟级降水预警 | 未来约 2 小时分钟降水有降水时为 on | `on` / `off`，属性含 summary |

> 旧版 `sensor.heweather_disaster_warn`（on/off 文本传感器）仍保留一版，方便旧自动化；新自动化请改用 binary_sensor。

### 灾害预警事件（推荐：逐条新增/解除通知）

除了 binary_sensor 属性变化，集成还会在预警 **新增** 或 **解除** 时 fire 专属 HA 事件，方便你按条播报：

| 事件名 | 时机 | payload |
|---|---|---|
| `heweather_disaster_new` | 有新增预警 | `text`（跟随 disastermsg 配置）、`text_long`（description）、`text_short`（headline）、`alerts`（原始列表） |
| `heweather_disaster_cleared` | 有预警被解除 | `text_short`（headline）、`alerts`（原始列表） |

**注意**：新增事件的 `text` 跟随集成配置——`allmsg` 时取 description（长文本），`title` 时取 headline（短文本）。`text_long` / `text_short` 始终携带，供自动化按需选择。

**API 故障保护**：天气预警 API 调用失败时，不会清空已有预警状态，也不会触发解除事件——避免误报。

#### 自动化示例：新增预警时语音播报（长文本）

```yaml
automation:
  - alias: 新增气象预警语音播报
    trigger:
      - platform: event
        event_type: hefeng_weather_disaster_new
    action:
      - action: notify.send_message
        target:
          entity_id:
            - notify.xiaomi_cn_795522484_l06a_play_text_a_5_1
            - notify.xiaomi_cn_866479630_oh2p_play_text_a_7_3
        data:
          message: "气象预警。{{ trigger.event.data.text_long }}"
```

#### 自动化示例：预警解除时语音播报（短文本）

```yaml
automation:
  - alias: 气象预警解除语音播报
    trigger:
      - platform: event
        event_type: hefeng_weather_disaster_cleared
    action:
      - action: notify.send_message
        target:
          entity_id:
            - notify.xiaomi_cn_795522484_l06a_play_text_a_5_1
            - notify.xiaomi_cn_866479630_oh2p_play_text_a_7_3
        data:
          message: "预警解除。{{ trigger.event.data.text_short }}"
```

#### 自动化示例：只关心新增、用短文本

```yaml
    action:
      - action: notify.send_message
        data:
          message: "新预警：{{ trigger.event.data.text_short }}"
```

#### 所有事件 payload 一览

**新增 `heweather_disaster_new`**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `text` | string | 跟随配置：`allmsg`→description，`title`→headline |
| `text_long` | string | description（长文本，适合语音/完整播报） |
| `text_short` | string | headline（短文本，适合快速通知） |
| `alerts` | list | 新增的原始预警对象列表 |
| `source` | string | `"heweather"` |

**解除 `heweather_disaster_cleared`**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `text_short` | string | headline（短文本） |
| `alerts` | list | 解除的原始预警对象列表 |
| `source` | string | `"heweather"` |

### 新增 sensor 摘要

- 分钟降水：`分钟降水描述`、`分钟降水强度`
- 天文：`日出`、`日落`、`月升`、`月落`、`月相`、`月亮照明度`
- 空气质量日预报：`明日空气质量级别` / `等级` / `首要污染物`
- 生活指数：补齐 `钓鱼指数`、`化妆指数`；修复太阳镜指数误绑紫外线的问题
- 污染物：补齐 `一氧化氮`、`非甲烷总烃`（API 有数据时）

### 自动化示例

```yaml
automation:
  - alias: 灾害预警通知（属性触发，兼容旧版）
    trigger:
      - platform: state
        entity_id: binary_sensor.he_feng_tian_qi_heweather_disaster_warn_binary
        attribute: states
    condition:
      - condition: state
        entity_id: binary_sensor.he_feng_tian_qi_heweather_disaster_warn_binary
        state: "on"
    action:
      - service: notify.mobile_app_xxx
        data:
          title: 灾害预警
          message: "{{ state_attr('binary_sensor.he_feng_tian_qi_heweather_disaster_warn_binary', 'states') }}"

  - alias: 一小时内有雨关窗提醒
    trigger:
      - platform: state
        entity_id: binary_sensor.he_feng_tian_qi_heweather_rain_warn
        to: "on"
    action:
      - service: notify.mobile_app_xxx
        data:
          message: "{{ state_attr('binary_sensor.he_feng_tian_qi_heweather_rain_warn', 'states') }}"
```

实体 ID 会随设备名变化，请在 HA 开发者工具 → 状态 中确认实际 `entity_id`。

### 未接入的付费 API

以下接口**不会**请求（按你的要求排除）：

- 热带气旋（台风）
- 海洋数据
- 太阳辐射 / 辐照

### 架构说明（2.5）

- 使用 `DataUpdateCoordinator` 统一拉取，避免 weather / sensor 重复请求实况
- 实况+空气+预警+预报+天文：约 10 分钟
- 生活指数：约 2 小时
- 分钟降水：约 10 分钟（失败不影响其它实体）
- 日/小时预报时间使用 API 返回的 `fxDate` / `fxTime`

