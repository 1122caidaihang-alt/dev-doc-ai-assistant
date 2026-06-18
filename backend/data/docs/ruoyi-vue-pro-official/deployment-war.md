# Tomcat WAR 部署

> 来源: https://doc.iocoder.cn/deployment-war

- [](/)
 - 开发指南
- 运维手册
 [芋道源码](https://www.iocoder.cn) [2025-08-21](javascript:;)    
# Tomcat WAR 部署
  
# # Tomcat 部署
 
友情提示：
 
参考 《Spring Boot 打包为 war 包，部署 tomcat》
 
 (opens new window)，已验证可行。
 
① 修改 `yudao-server` 目录的 `pom.xml` 文件，添加 `war` 包的打包配置：
 
```
 -->
packaging>warpackaging>

```

继续修改该 `pom.xml` 文件，添加 `spring-boot-starter-tomcat` 依赖：
 
```
        
        dependency>
            groupId>org.springframework.bootgroupId>
            artifactId>spring-boot-starter-webartifactId>
            exclusions>
                exclusion>
                    groupId>org.springframework.bootgroupId>
                    artifactId>spring-boot-starter-tomcatartifactId>
                exclusion>
            exclusions>
        dependency>

        
        dependency>
            groupId>org.springframework.bootgroupId>
            artifactId>spring-boot-starter-tomcatartifactId>
            scope>providedscope>
        dependency>

```

② 修改 YudaoServerApplication 类，实现 SpringBootServletInitializer 接口，并重写 `configure` 方法：
 
```

    /**
     * 用于 WAR 包部署到外部 Tomcat
     */
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(YudaoServerApplication.class);
    }

```

③ 根目录执行打包命令：
 
```
mvn clean package -Dmaven.test.skip=true

```

后续，部署到 Tomcat 的时候，使用 `yudao-server/target/yudao-server.war` 文件。
 
注意，`context-path` 需要为 `/` 噢！
 
# # 国产 TongWeb 部署
 
友情提示：最好上面的 Tomcat 部署先跑通！！！
 
手头暂时没有 TongWeb 的环境，无法验证是否可行。目前找了几篇看着还行的文档：
 - 《国产化：springboot 项目 TongWeb 替换 tomcat 踩坑实录 》
 
 (opens new window)
 - 《Springboot 集成东方通等中间件打包和部署》
 
 (opens new window)
 - 《信创改造：tongweb 部署 Springboot 项目方案>》
 
 (opens new window)
 
  
  
    .pageB img{width:80px!important;}
    .wwads-horizontal .wwads-text, .wwads-content .wwads-text{line-height:1;}
  
    [服务监控](/server-monitor/) [开发规范](/vue3/dev-spec/) 

        ←
        [服务监控](/server-monitor/) [开发规范](/vue3/dev-spec/)→