# ERP 演示

> 来源: https://doc.iocoder.cn/erp-preview

- [](/)
 - 开发指南
- ERP手册
 [芋道源码](https://www.iocoder.cn) [2024-02-16](javascript:;)   目录  
# ERP 演示
  
## # 1. 演示地址
 
### # 1.1 ERP 管理后台
 - 演示地址：http://dashboard-vue3.yudao.iocoder.cn/
 
 (opens new window)
 - 菜单：“ERP 系统”下的「采购管理」「销售管理」「库存管理」「产品管理」「财务管理」
 - 仓库：https://github.com/yudaocode/yudao-ui-admin-vue3
 
 (opens new window) 的 `erp` 目录，基于 Vue3 + Element Plus 实现
 

 
### # 1.2 ERP 后端
 
支持 Spring Boot 单体、Spring Cloud 微服务架构
 - 单体仓库： https://github.com/YunaiV/ruoyi-vue-pro
 
 (opens new window) 的 `yudao-module-erp` 模块
 - 微服务仓库： https://github.com/YunaiV/yudao-cloud
 
 (opens new window) 的 `yudao-module-erp` 服务
 
## # 2. ERP 启动
 
参见 [《ERP 手册 —— 功能开启》](/erp/build/) 文档，一般 3 分钟就可以启动完成。
 
## # 3. ERP 交流
 
专属交流社区，欢迎扫码加入。
 

 
## # 4. 功能描述
 
主要分为 5 个核心模块：采购、销售、库存、产品、财务。
 

 
## # 5. 表结构
 
ERP 一共有 **30+** 张表，具备一定的业务复杂度，对提升技术能力会有不错的帮助，平时做项目也可以参考参考。
 
### # 5.1 采购管理
 
以 `erp_purchase_` 作为前缀的表，表结构如下：
 

 - [《【采购】采购订单、入库、退货》](/erp/purchase/)
 
### # 5.2 销售管理
 
以 `erp_sale_` 作为前缀的表，表结构如下：
 

 - [《【销售】销售订单、出库、退货》](/erp/sale/)
 
### # 5.3 库存管理
 
以 `erp_stock_` 作为前缀的表，表结构如下：
 

 - [《【库存】产品库存、库存明细》](/erp/stock/)
 - [《【库存】其它入库、其它出库》](/erp/stock-in-out/)
 - [《【库存】库存调拨、库存盘点》](/erp/stock-move-check/)
 
### # 5.4 产品管理
 
以 `erp_product_` 作为前缀的表，表结构如下：
 

 - [《【产品】产品信息、分类、单位》](/erp/product/)
 
### # 5.5 财务管理
 
以 `erp_finance_` 作为前缀的表，表结构如下：
 

 - [《【财务】采购付款、销售收款》](/erp/finance-payment-receipt/)
 
  
  
    .pageB img{width:80px!important;}
    .wwads-horizontal .wwads-text, .wwads-content .wwads-text{line-height:1;}
  
    [【统计】会员、商品、交易统计](/mall/statistics/) [功能开启](/erp/build/) 

        ←
        [【统计】会员、商品、交易统计](/mall/statistics/) [功能开启](/erp/build/)→