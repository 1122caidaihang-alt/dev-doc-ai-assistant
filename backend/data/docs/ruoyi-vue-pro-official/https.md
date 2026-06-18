# HTTPS 证书

> 来源: https://doc.iocoder.cn/https

- [](/)
 - 开发指南
- 运维手册
 [芋道源码](https://www.iocoder.cn) [2022-04-16](javascript:;)   目录  
# HTTPS 证书
  
本小节，讲解如何在 Nginx 配置 SSL 证书，实现前端和后端使用 HTTPS 安全访问的功能。
 
考虑到各大云服务厂商的文档写的比较齐全，这里更多做汇总与整理。
 
😜 如果想要免费的 SSL 证书，请申请 DV 单域名证书。如果要配置多个域名，可以申请多个 DV 单域名证书。
 
友情提示：HTTPS 的学习资料？
 - 《HTTPS 的工作原理》
 
 (opens new window)
 - 《面试官：你连 HTTPS 原理没搞懂，还给我讲“中间人攻击”？》
 
 (opens new window)
 
重要！有个球友共享了 https://t.zsxq.com/th7np
 
 (opens new window) 了他的配置过程，大家可以借鉴下！
 
## # 1. 阿里云 SSL【最常用】
 
阿里云 SSL 证书
 
 (opens new window)
 - 第一步，免费证书申购流程
 
 (opens new window)
 - 第二步，在 Nginx 或 Tengine 服务器上安装证书
 
 (opens new window)
 

 
↑ 点击观看 ↑
 
 (opens new window)

## # 2. FreeSSL【最便宜】
 
FreeSSL.cn
 
 (opens new window)，一个提供免费 HTTPS 证书申请的网站。
 
《如何在 Nginx/Apache/Tomcat/IIS 自动部署证书？》
 
 (opens new window)
 
疑问：有没其它类似的平台？
 - OHTTPS
 
 (opens new window)：免费提供 HTTPS 证书，支持一键申请、自动更新、自动部署的功能。
 
## # 3. 腾讯云 SSL
 
腾讯云 SSL 证书
 
 (opens new window)
 - 第一步，免费 SSL 证书申请流程
 
 (opens new window)
 - 第二步，Nginx 服务器 SSL 证书安装部署
 
 (opens new window)
 

 
↑ 点击观看 ↑
 
 (opens new window)

## # 4. 华为云 SSL
 
云证书管理服务 CCM
 
 (opens new window)
 - 第一步，SSL 证书申购流程
 
 (opens new window)
 - 第二步，下载与安装 SSL 证书
 
 (opens new window)
 
  
  
    .pageB img{width:80px!important;}
    .wwads-horizontal .wwads-text, .wwads-content .wwads-text{line-height:1;}
  
    [1Panel 部署](/deployment-1panel/) [服务监控](/server-monitor/) 

        ←
        [1Panel 部署](/deployment-1panel/) [服务监控](/server-monitor/)→