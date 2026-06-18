# 工具类 Util

> 来源: https://doc.iocoder.cn/util

- [](/)
 - 开发指南
- 后端手册
 [芋道源码](https://www.iocoder.cn) [2022-04-04](javascript:;)   目录  
# 工具类 Util
  
本小节，介绍项目中使用到的工具类，避免大家重复造轮子。
 
## # 1. Hutool
 
项目使用 Hutool
 
 (opens new window) 作为主工具库。Hutool 是国产的一个 Java 工具包，它可以帮助我们简化每一行代码，减少每一个方法，让 Java 语言也可以“甜甜的”。
 
`yudao-common`
 
 (opens new window) 模块的 `util`
 
 (opens new window) 包作为辅工具库，以 Utils 结尾，补充 Hutool 缺少的工具能力。
 
友情提示：常用的工具类，使用 ⭐ 标记，需要的时候可以找找有没对应的工具方法。
 作用 Hutool 芋道 Utils 数组工具 ArrayUtil
 
 (opens new window) ArrayUtils
 
 (opens new window) ⭐ 集合工具 CollUtil
 
 (opens new window) CollectionUtils
 
 (opens new window) ⭐ Map 工具 MapUtil
 
 (opens new window) MapUtils
 
 (opens new window) Set 工具  SetUtils
 
 (opens new window) List 工具 ListUtil
 
 (opens new window)  文件工具 FileUtil
 
 (opens new window) 
 FileTypeUtil
 
 (opens new window) FileUtils
 
 (opens new window) 压缩工具 ZipUtil
 
 (opens new window) IoUtils
 
 (opens new window) IO 工具 ZipUtil
 
 (opens new window)  Resource 工具 ResourceUtil
 
 (opens new window)  JSON 工具  JsonUtils
 
 (opens new window) 数字工具 NumberUtil
 
 (opens new window) NumberUtils
 
 (opens new window) 对象工具 ObjectUtil
 
 (opens new window) ObjectUtils
 
 (opens new window) 唯一 ID 工具 IdUtil
 
 (opens new window)  ⭐ 字符串工具 StrUtil
 
 (opens new window) StrUtils
 
 (opens new window) 时间工具 DateUtil
 
 (opens new window) DateUtils
 
 (opens new window) 反射工具 ReflectUtil
 
 (opens new window)  异常工具 ExceptionUtil
 
 (opens new window)  随机工具 RandomUtil
 
 (opens new window) RandomUtils
 
 (opens new window) URL 工具 URLUtil
 
 (opens new window) HttpUtils
 
 (opens new window) Servlet 工具  ServletUtils
 
 (opens new window) Spring 工具 SpringUtil
 
 (opens new window) SpringExpressionUtils
 
 (opens new window) 分页工具  PageUtils
 
 (opens new window) 校验工具 ValidationUtil
 
 (opens new window) ValidationUtils
 
 (opens new window) 断言工具 Assert
 
 (opens new window) AssertUtils
 
 (opens new window) 
强烈推荐：
 
Guava 是 Google 开源的 Java 常用类库，如果你感兴趣，可以阅读 《Guava 学习笔记》
 
 (opens new window) 文章。
 
## # 2. Lombok
 
Lombok
 
 (opens new window) 是一个 Java 工具，通过使用其定义的注解，自动生成常见的冗余代码，提升开发效率。
 
如果你没有学习过 Lombok，需要阅读下 《芋道 Spring Boot 消除冗余代码 Lombok 入门》
 
 (opens new window) 文章。
 
在项目的根目录有 `lombok.config`
 
 (opens new window) 全局配置文件，开启链式调用、生成的 toString/hashcode/equals 方法需要调用父方法。如下图所示：
 

 
## # 3. HTTP 调用
 
① 使用 Feign 实现声明式的调用，可参考《芋道 Spring Boot 声明式调用 Feign 入门 》
 
 (opens new window)文章。
 
② 使用 Hutool 自带的 HttpUtil
 
 (opens new window) 工具类。
 
  
  
    .pageB img{width:80px!important;}
    .wwads-horizontal .wwads-text, .wwads-content .wwads-text{line-height:1;}
  
    [验证码](/captcha/) [配置管理](/config-center/) 

        ←
        [验证码](/captcha/) [配置管理](/config-center/)→