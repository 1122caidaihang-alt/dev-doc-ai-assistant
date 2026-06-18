# Webhook（钉钉、飞书、企微）

> 来源: https://doc.iocoder.cn/webhook

- [](/)
 - 开发指南
- 系统手册
 [芋道源码](https://www.iocoder.cn) [2025-11-26](javascript:;)   目录  
# Webhook（钉钉、飞书、企微）
  
## # 1. 现状
 
目前项目中，暂时没有直接集成 Webhook 功能~~~原因是：
 - 第一，Webhook 的需求量暂时不太大，很少有 GitHub Issue 或者星球用户提出相关需求，所以不想增加 `system` 模块的复杂性
 - 第二，暂时没想到一个类似 [《短信配置》](/sms/) 这种形式，可以把钉钉、飞书、企微等 Webhook 平台统一起来，方便用户配置和使用
 
当然，项目本身其实有比较精简的 Webhook 功能，比如：
 - DebugDingTalkSmsClient 类，模拟短信发送，使用钉钉机器人来接收消息
 - 有球友 《Pull Request：添加钉钉机器人消息发送功能》
 
 (opens new window) + #788
 
 (opens new window)，一起聊过也不算特别满意
 
## # 2. 期望
 
① 类似 https://github.com/terminux/ding-talk-spring-boot
 
 (opens new window) 这种形式，但是需要额外：
 - 支持飞书、企微等平台
 - 不仅仅支持 yaml 配置文件，也支持数据库配置（类似短信配置）
 
其它相似项目：
 - 飞书：https://gitee.com/fandylin/feishu-alert-robot-starter
 
 (opens new window)
 - 企微：https://github.com/group-robot/work-weixin-robot-java
 
 (opens new window)
 
② 类似 https://github.com/ymlluo/group-robot
 
 (opens new window) 这种形式，但是它是 PHP 实现，需要有 Java 版本。
 
  
  
    .pageB img{width:80px!important;}
    .wwads-horizontal .wwads-text, .wwads-content .wwads-text{line-height:1;}
  
    [站内信配置](/notify/) [数据脱敏、字段权限](/desensitize/) 

        ←
        [站内信配置](/notify/) [数据脱敏、字段权限](/desensitize/)→