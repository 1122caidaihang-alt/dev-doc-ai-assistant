# 配置读取

> 来源: https://doc.iocoder.cn/vue3/config-center

- [](/)
 - 开发指南
- 前端手册 Vue 3.x
 [芋道源码](https://www.iocoder.cn) [2023-04-07](javascript:;)   目录  
# 配置读取
  
在 [基础设施 -> 配置管理] 菜单，可以动态修改配置，无需重启服务器即可生效。
 

 
提示
 
对应 [《后端手册 —— 配置中心》](/config-center/) 文档。
 
## # 1. 读取配置
 
前端调用 `/@api/infra/config/index.ts`
 
 (opens new window) 的 `#getConfigKey(configKey)` 方法，获取指定 key 对应的配置的值。代码如下：
 
```
// 根据参数键名查询参数值
export const getConfigKey = (configKey: string) => {
    return request.get({ url: '/infra/config/get-value-by-key?key=' + configKey })
}

```

## # 2. 实战案例
 
在 `src/views/infra/server/index.vue`
 
 (opens new window) 页面中，获取 key 为 `"url.skywalking"` 的配置的值。代码如下：
 

 
  
  
    .pageB img{width:80px!important;}
    .wwads-horizontal .wwads-text, .wwads-content .wwads-text{line-height:1;}
  
    [通用方法](/vue3/util/) [CRUD 组件](/vue3/crud-schema/) 

        ←
        [通用方法](/vue3/util/) [CRUD 组件](/vue3/crud-schema/)→