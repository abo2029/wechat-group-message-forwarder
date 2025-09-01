##############group_message_forwarder.py: [群消息转发器 V2] ################
# 变更记录: [2025-09-01 07:45] @abo2029 [V2版本：新增多群转发功能，支持同时监听多个群并转发到各自目标] ########
# 变更记录: [2025-09-01 05:36] @abo2029 [移除图片大小限制] ########
# 变更记录: [2025-09-01 05:33] @abo2029 [优化图片转发稳定性] ########
# 变更记录: [2025-06-30 00:25] @李祥光 [修复WindowsPath对象错误] ########
# 变更记录: [2024-12-29 23:50] @李祥光 [移除错误的group属性判断] ########
# 变更记录: [2024-12-29 23:45] @李祥光 [修复消息过滤逻辑] ########
# 变更记录: [2024-12-29 23:40] @李祥光 [修复图片消息转发] ########

###########################文件下的所有函数###########################
"""
log_info：记录正常信息日志到文件并以绿色打印到控制台
log_error：记录错误日志到文件并以红色打印到控制台
load_forward_config：从配置文件读取多群转发配置（多个源群和对应目标群列表）
forward_message_to_groups：将消息转发到指定的目标群列表，支持文本和图片
message_callback：处理接收到的消息，转发文字和图片类型消息
main：主函数，初始化微信客户端并监听多个群消息
"""
###########################文件下的所有函数###########################

#########mermaid格式说明所有函数的调用关系说明开始#########
"""
flowchart TD
    A[程序启动] --> B[main函数]
    B --> C[初始化微信实例]
    C --> D[load_forward_config加载多群转发配置]
    D --> E[为每个源群设置消息监听]
    E --> F[message_callback]
    F --> G{判断消息类型}
    G -->|文字消息| H[forward_message_to_groups文本转发]
    G -->|图片消息| I[forward_message_to_groups图片转发]
    G -->|其他消息| K[忽略消息]
    H --> L[发送文本到对应目标群列表]
    I --> M[发送图片到对应目标群列表]
"""
#########mermaid格式说明所有函数的调用关系说明结束#########

from wxauto import WeChat
import wxauto
import traceback
import time
import logging
import os
import sys
import concurrent.futures
import threading
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('group_forwarder.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 配置参数
IMAGE_DOWNLOAD_TIMEOUT = 60  # 图片下载超时时间（秒）
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 2  # 重试间隔（秒）

def log_info(info_msg):
    """记录正常信息日志到文件并以绿色打印到控制台"""
    with open('group_forwarder.log', 'a', encoding='utf-8') as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] INFO: {info_msg}\n")
    print(f"\033[92m[{time.strftime('%Y-%m-%d %H:%M:%S')}] {info_msg}\033[0m")
    logging.info(info_msg)

def log_error(error_msg):
    """记录错误日志到文件并以红色打印到控制台"""
    with open('group_forwarder_error.log', 'a', encoding='utf-8') as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {error_msg}\n")
    print(f"\033[91m[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {error_msg}\033[0m")
    logging.error(error_msg)

def load_forward_config(config_file="forward_config.txt"):
    """从配置文件读取多群转发配置"""
    config = {}
    
    try:
        if not os.path.exists(config_file):
            log_error(f"配置文件不存在: {config_file}")
            default_config = """# 群消息转发配置文件
# 格式说明：
# 每个转发组用空行分隔
# 每组第一行为源群名称
# 后续行为该源群对应的目标群列表
# 以#开头的行为注释

# 第一组转发配置
测试群1
目标群A
目标群B
目标群C

# 第二组转发配置
测试群2
目标群D
目标群E"""
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write(default_config)
            log_info(f"已创建默认配置文件: {config_file}，请修改后重新运行程序")
            return config
        
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 按空行分割不同的转发组
        groups = [group.strip() for group in content.split('\n\n') if group.strip()]
        
        for group in groups:
            lines = [line.strip() for line in group.split('\n') 
                    if line.strip() and not line.strip().startswith('#')]
            if lines:
                source_group = lines[0]
                target_groups = lines[1:]
                if target_groups:  # 只添加有目标群的配置
                    config[source_group] = target_groups
                    log_info(f"加载转发配置 - 源群: {source_group}, 目标群: {target_groups}")
        
        if not config:
            log_error("配置文件中没有找到有效的转发配置")
            return config
        
        log_info(f"成功读取所有转发配置，共 {len(config)} 个源群")
        return config
        
    except Exception as e:
        log_error(f"读取配置文件失败: {str(e)}")
        return config

def verify_file_integrity(file_path):
    """验证文件完整性"""
    try:
        if not os.path.exists(file_path):
            return False, "文件不存在"
        
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return False, "文件大小为0"
            
        return True, "文件验证通过"
    except Exception as e:
        return False, f"文件验证失败: {str(e)}"

def download_image_with_retry(msg):
    """带重试机制的图片文件下载"""
    for attempt in range(MAX_RETRIES):
        try:
            def download_task():
                try:
                    return msg.download()
                except Exception as e:
                    log_error(f"图片下载任务异常: {str(e)}")
                    return None

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(download_task)
                try:
                    download_result = future.result(timeout=IMAGE_DOWNLOAD_TIMEOUT)
                    
                    if download_result:
                        if isinstance(download_result, dict):
                            if download_result.get('status') == '失败':
                                raise Exception(download_result.get('message', '未知错误'))
                            download_path = download_result.get('data')
                        else:
                            download_path = str(download_result)

                        # 验证文件
                        is_valid, message = verify_file_integrity(download_path)
                        if not is_valid:
                            raise Exception(message)

                        log_info(f"图片下载成功: {download_path}")
                        return download_path
                    else:
                        raise Exception("下载返回空结果")
                        
                except concurrent.futures.TimeoutError:
                    log_error(f"图片下载超时 (尝试 {attempt + 1}/{MAX_RETRIES})")
                    raise
                
        except Exception as e:
            log_error(f"图片下载失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {str(e)}")
            if attempt < MAX_RETRIES - 1:
                log_info(f"等待 {RETRY_DELAY} 秒后重试...")
                time.sleep(RETRY_DELAY)
            else:
                raise Exception(f"图片下载失败，已达到最大重试次数")
    
    return None

def forward_message_to_groups(wx, message_content, sender_name, target_groups, message_type='text'):
    """将消息转发到指定的目标群列表"""
    try:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        success_count = 0
        
        for target_group in target_groups:
            try:
                wx.ChatWith(target_group)
                
                if message_type == 'text':
                    formatted_message = f"[转发消息]\n发送人：{sender_name}\n发送时间：{current_time}\n\n{message_content}"
                    wx.SendMsg(formatted_message)
                    log_info(f"文本消息已转发到群: {target_group}")
                elif message_type == 'image':
                    info_message = f"[转发图片]\n发送人：{sender_name}\n发送时间：{current_time}"
                    wx.SendMsg(info_message)
                    
                    file_path = str(message_content)
                    if os.path.exists(file_path):
                        wx.SendFiles(file_path)
                        log_info(f"图片消息已转发到群: {target_group}")
                    else:
                        log_error(f"图片文件不存在: {file_path}")
                        continue
                else:
                    log_error(f"不支持的消息类型: {message_type}")
                    continue
                    
                success_count += 1
                time.sleep(0.5)  # 添加短暂延迟避免消息发送过快
            except Exception as e:
                log_error(f"转发消息到群 {target_group} 失败: {str(e)}")
        
        log_info(f"消息转发完成，成功转发到 {success_count}/{len(target_groups)} 个群")
        
    except Exception as e:
        log_error(f"转发消息时出现异常: {str(e)}\n{traceback.format_exc()}")

def cleanup_temp_file(file_path):
    """清理临时文件"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            log_info(f"临时文件已删除: {file_path}")
    except Exception as e:
        log_error(f"删除临时文件失败: {str(e)}")

def message_callback(msg, chat, wx, target_groups):
    """处理接收到的消息"""
    try:
        log_info(f"收到来自 {msg.sender} 的消息: {msg.content}")
        log_info(f"消息类型: {msg.type}")
        
        if msg.type == 'text':
            if msg.content and msg.content.strip():
                forward_message_to_groups(wx, msg.content, msg.sender, target_groups, 'text')
            else:
                log_info("消息内容为空，跳过转发")
                
        elif msg.type == 'image':
            log_info("检测到图片消息，准备下载...")
            
            try:
                download_path = download_image_with_retry(msg)
                if download_path:
                    forward_message_to_groups(wx, download_path, msg.sender, target_groups, 'image')
                    cleanup_temp_file(download_path)
            except Exception as e:
                log_error(f"图片处理失败: {str(e)}")
                
        else:
            log_info(f"不支持的消息类型: {msg.type}，跳过转发")
            
    except Exception as e:
        log_error(f"消息处理主异常: {str(e)}\n{traceback.format_exc()}")

def main():
    """主程序入口"""
    try:
        log_info("=== 微信群消息转发器 V2 启动 ===")
        log_info("支持多群监听和分发功能")
        
        # 加载配置
        forward_config = load_forward_config()
        if not forward_config:
            log_error("转发配置无效，请检查配置文件")
            return
        
        try:
            wx = WeChat()
            if wx is None:
                raise Exception("微信实例初始化失败，返回None")
            log_info("微信实例初始化成功")
        except Exception as e:
            log_error(f"微信实例初始化失败: {str(e)}")
            log_error("请确保：1. 微信已登录 2. 微信客户端正常运行")
            return
        
        # 为每个源群添加监听
        for source_group, target_groups in forward_config.items():
            try:
                if not hasattr(wx, 'AddListenChat'):
                    raise Exception("微信实例无效，缺少AddListenChat方法")

                def create_callback(target_groups):
                    def callback_with_params(msg, chat):
                        message_callback(msg, chat, wx, target_groups)
                    return callback_with_params

                wx.AddListenChat(nickname=source_group, 
                               callback=create_callback(target_groups))
                log_info(f"已添加监听源群: {source_group} -> {len(target_groups)}个目标群")

            except Exception as e:
                log_error(f"添加监听失败 {source_group}: {str(e)}")
                if "NoneType" in str(e) or "NativeWindowHandle" in str(e):
                    log_error("检测到微信实例异常，建议重启程序")
                continue
        
        log_info(f"成功配置 {len(forward_config)} 个源群的监听")
        log_info("开始监听群消息并自动转发...")
        log_info("程序运行中，按 Ctrl+C 停止程序")
        
        if wx is not None and hasattr(wx, 'KeepRunning'):
            wx.KeepRunning()
        else:
            log_error("微信实例无效，无法保持运行状态")
            return
        
    except KeyboardInterrupt:
        log_info("用户手动停止程序")
    except Exception as e:
        log_error(f"程序运行出错: {str(e)}\n{traceback.format_exc()}")
    finally:
        log_info("=== 微信群消息转发器 V2 结束 ===")

if __name__ == "__main__":
    main()
