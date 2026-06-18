# 内网穿透

> 来源: https://doc.iocoder.cn/natapp

- [](/)
 - 开发指南
- 萌新必读
 [芋道源码](https://www.iocoder.cn) [2023-07-10](javascript:;)   目录  
# 内网穿透
  
在和外部系统对接时，经常需要将本地的服务，暴露到外网中。这时候，就需要使用内网穿透工具了。例如说：支付宝回调、微信支付回调、微信公众号接入、微信小程序接入等等。
 
常见的内网穿透工具，例如说，ngrok
 
 (opens new window)、frp
 
 (opens new window)、natapp
 
 (opens new window) 等等。
 
这里，我们使用 natapp 作为内网穿透工具，转发到后端的 48080 端口。
 
## # 1. 第一步，购买隧道
 
访问 https://natapp.cn/tunnel/buy/free
 
 (opens new window) 地址，免费购买一个隧道。如下图所示：
 

 
## # 2. 第二步，启动隧道
 
购买完成后，参考 《NATAPP 1 分钟快速新手图文教程》
 
 (opens new window) 文档，将 natapp 进行启动。如下图所示：
 

 
  
  
    .pageB img{width:80px!important;}
    .wwads-horizontal .wwads-text, .wwads-content .wwads-text{line-height:1;}
  
    [如何去除 Redis 缓存](/remove-redis/) [面试题、简历模版、简历优化](/interview/) 

        ←
        [如何去除 Redis 缓存](/remove-redis/) [面试题、简历模版、简历优化](/interview/)→