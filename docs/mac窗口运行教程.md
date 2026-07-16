 # mac教程

> 1.  打开终端，解压分发的压缩包：
>     
>     **选项1：解压到系统目录（需要管理员权限）**
>     
>     ```shell
>     sudo mkdir -p /usr/local/bin/MAA_MHXY_SK
>     sudo tar -xzf <下载的MAA_MHXY_SK压缩包路径> -C /usr/local/bin/MAA_MHXY_SK
>     ```
>     
>     **选项2：解压到用户目录（推荐，无需sudo）**
>     
>     ```shell
>     mkdir -p ~/MAA_MHXY_SK
>     tar -xzf <下载的MAA_MHXY_SK压缩包路径> -C ~/MAA_MHXY_SK
>     ```
>     
> 2.  进入解压目录并运行程序：
>     
>     ```shell
>     cd /usr/local/bin/MAA_MHXY_SK
>     ./MAA_MHXY_SK
>     ```
>     
> 
> 若想使用**图形操作页面**请按第二步操作，执行 `MAA_MHXY_SK` 程序。
> 
> ⚠️Gatekeeper 安全提示处理：
> 
> 在 macOS 10.15 (Catalina) 及更高版本中，Gatekeeper 可能会阻止运行未签名的应用程序。  
> 如果遇到"无法打开，因为无法验证开发者"等错误，请选择以下任一方案:
> 
> ```shell
> # 方案1：以 MAA_MHXY_SK 为例，移除隔离属性（推荐，以实际路径为准）
> sudo xattr -rd com.apple.quarantine /usr/local/bin/MAA_MHXY_SK/MAA_MHXY_SK
> # 或用户目录版本：xattr -rd com.apple.quarantine ~/MAA_MHXY_SK/MAA_MHXY_SK
> 
> # 方案2：添加到 Gatekeeper 白名单
> sudo spctl --add /usr/local/bin/MAA_MHXY_SK/MAA_MHXY_SK
> # 或用户目录版本：spctl --add ~/MAA_MHXY_SK/MAA_MHXY_SK
> 
> # 方案3：一次性处理整个目录
> sudo xattr -rd com.apple.quarantine /usr/local/bin/MAA_MHXY_SK/*
> # 或用户目录版本：xattr -rd com.apple.quarantine ~/MAA_MHXY_SK/*
> ```