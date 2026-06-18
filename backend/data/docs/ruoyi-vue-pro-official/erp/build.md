# 功能开启

> 来源: https://doc.iocoder.cn/erp/build

- [](/)
 - 开发指南
- ERP手册
 [芋道源码](https://www.iocoder.cn) [2024-02-16](javascript:;)   目录  
# 功能开启
  
进度说明：
 - 管理后台，请使用 https://gitee.com/yudaocode/yudao-ui-admin-vue3
 
 (opens new window) 仓库的 `master` 分支
 - 后端项目，请使用 https://gitee.com/zhijiantianya/ruoyi-vue-pro
 
 (opens new window) 仓库的 `master`（JDK8） 或 `master-jdk17`（JDK17//21） 分支
 
ERP 系统，后端由 `yudao-module-erp` 模块实现，前端由 `yudao-ui-admin-vue3` 的 `erp` 目录实现。
 
考虑到编译速度，默认 `yudao-module-erp` 模块是关闭的，需要手动开启。步骤如下：
 - 第一步，开启 `yudao-module-erp` 模块
 - 第二步，导入 ERP 系统的 SQL 数据库脚本
 - 第三步，重启后端项目，确认功能是否生效
 
## # 1. 第一步，开启模块
 
① 修改根目录的 `pom.xml`
 
 (opens new window) 文件，取消 `yudao-module-erp` 模块的注释。如下图所示：
 

 
② 修改 `yudao-server` 目录的 `pom.xml`
 
 (opens new window) 文件，引入 `yudao-module-erp` 模块。如下图所示：
 

 
③ 点击 IDEA 右上角的【Reload All Maven Projects】，刷新 Maven 依赖。如下图所示：
 

 
## # 2. 第二步，导入 SQL
 
点击 `erp-2024-05-03.sql.zip`
 
 (opens new window) 下载附件，解压出 SQL 文件，然后导入到数据库中。 如下图所示：
 
友情提示：↑↑↑ erp.sql 是可以点击下载的！ ↑↑↑
 
重要说明：该 SQL 仅芋道星球成员可使用和商用，否则视为侵权（索赔 100 万，永久追溯）【下载即视为同意】。
 

 
以 `erp_` 作为前缀的表，就是 ERP 模块的表。
 
## # 3. 第三步，重启项目
 
重启后端项目，然后访问前端的 ERP 菜单，确认功能是否生效。如下图所示：
 

 
至此，我们就成功开启了 ERP 的功能 🙂
 
  
  
    .pageB img{width:80px!important;}
    .wwads-horizontal .wwads-text, .wwads-content .wwads-text{line-height:1;}
  
    [ERP 演示](/erp-preview/) [【产品】产品信息、分类、单位](/erp/product/) 

        ←
        [ERP 演示](/erp-preview/) [【产品】产品信息、分类、单位](/erp/product/)→