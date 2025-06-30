##############group_message_forwarder.py: [群消息转发器] ################
# 变更记录: [2025-06-30 09:40] @李祥光 [修复视频下载超时问题：使用ThreadPoolExecutor实现2分钟超时控制，避免大视频文件下载时间过长导致程序阻塞]########
# 变更记录: [2025-06-30 00:25] @李祥光 [修复WindowsPath对象错误：在图片和视频转发时将路径对象转换为字符串，解决SendFiles方法的类型错误]########
# 变更记录: [2024-12-29 23:50] @李祥光 [移除错误的group属性判断：根据wxauto官方文档，消息类型无group属性，改为处理所有消息类型]########
# 变更记录: [2024-12-29 23:45] @李祥光 [修复消息过滤逻辑：恢复群消息判断条件，确保只处理群消息]########
# 变更记录: [2024-12-29 23:40] @李祥光 [修复图片和视频消息转发：使用msg.download()正确下载临时文件，转发后自动清理]########
# 变更记录: [2025-06-29 22:30] @李祥光 [新增图片和视频消息转发功能：支持监听并转发图片、视频类型消息到目标群列表]########
# 变更记录: [2025-06-29 22:10] @李祥光 [修复wxautox API调用错误：使用ChatWith和SendMsg替代不存在的GetChat方法]########
# 变更记录: [2025-06-29] @李祥光 [修复转发消息时的SendMsg方法调用错误：正确获取聊天窗口对象]########
# 变更记录: [2025-01-20] @李祥光 [创建群消息转发功能：监听指定群的文字消息并转发到目标群列表]########
# 输入: [指定群的文字、图片、视频消息] | 输出: [转发到目标群列表]###############

###########################文件下的所有函数###########################
"""
log_info：记录正常信息日志到文件并以绿色打印到控制台
log_error：记录错误日志到文件并以红色打印到控制台
load_forward_config：从配置文件读取转发配置（源群和目标群列表）
forward_message_to_groups：将消息转发到指定的目标群列表，支持文本、图片和视频消息
message_callback：处理接收到的消息，转发文字、图片和视频类型消息
main：主函数，初始化微信客户端并监听消息
"""
###########################文件下的所有函数###########################

#########mermaid格式说明所有函数的调用关系说明开始#########
"""
flowchart TD
    A[程序启动] --> B[main函数]
    B --> C[初始化微信实例]
    C --> D[load_forward_config加载转发配置]
    D --> E[设置消息监听]
    E --> F[message_callback]
    F --> G{判断消息类型}
    G -->|文字消息| H[forward_message_to_groups文本转发]
    G -->|图片消息| I[forward_message_to_groups图片转发]
    G -->|视频消息| J[forward_message_to_groups视频转发]
    G -->|其他消息| K[忽略消息]
    H --> L[发送文本到目标群列表]
    I --> M[发送图片到目标群列表]
    J --> N[发送视频到目标群列表]
"""
#########mermaid格式说明所有函数的调用关系说明结束#########

from wxautox import WeChat  # 这里就是wxautox库，不要改成wxauto
import wxautox
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

def log_info(info_msg):
    """
    log_info 功能说明:
    # 记录正常信息日志到文件并以绿色打印到控制台
    # 输入: info_msg(str) - 信息内容 | 输出: None
    """
    with open('group_forwarder.log', 'a', encoding='utf-8') as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] INFO: {info_msg}\n")
    # 绿色输出正常信息
    print(f"\033[92m[{time.strftime('%Y-%m-%d %H:%M:%S')}] {info_msg}\033[0m")
    logging.info(info_msg)

def log_error(error_msg):
    """
    log_error 功能说明:
    # 记录错误日志到文件并以红色打印到控制台
    # 输入: error_msg(str) - 错误信息 | 输出: None
    """
    with open('group_forwarder_error.log', 'a', encoding='utf-8') as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {error_msg}\n")
    # 红色输出错误信息
    print(f"\033[91m[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {error_msg}\033[0m")
    logging.error(error_msg)

def load_forward_config(config_file="forward_config.txt"):
    """
    load_forward_config 功能说明:
    # 从配置文件读取转发配置，包括源群和目标群列表
    # 输入: config_file (str) 配置文件路径 | 输出: dict 包含source_group和target_groups的配置字典
    """
    config = {
        'source_group': None,
        'target_groups': []
    }
    
    try:
        if not os.path.exists(config_file):
            log_error(f"配置文件不存在: {config_file}")
            # 创建默认配置文件
            default_config = """# 群消息转发配置文件
# 第一行：源群名称（要监听的群）
# 后续行：目标群名称列表（要转发到的群，每行一个）
# 以#开头的行为注释行

# 源群（监听此群的消息）
源群名称

# 目标群列表（转发到这些群）
目标群1
目标群2
目标群3"""
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write(default_config)
            log_info(f"已创建默认配置文件: {config_file}，请修改后重新运行程序")
            return config
        
        with open(config_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip() and not line.strip().startswith('#')]
        
        if not lines:
            log_error("配置文件中没有找到有效的配置")
            return config
        
        # 第一行是源群
        config['source_group'] = lines[0]
        log_info(f"源群: {config['source_group']}")
        
        # 后续行是目标群列表
        if len(lines) > 1:
            config['target_groups'] = lines[1:]
            log_info(f"目标群列表: {config['target_groups']}")
        else:
            log_error("配置文件中没有找到目标群")
        
        log_info(f"成功读取转发配置: 源群={config['source_group']}, 目标群数量={len(config['target_groups'])}")
        return config
        
    except Exception as e:
        log_error(f"读取配置文件失败: {str(e)}")
        return config

def forward_message_to_groups(wx, message_content, sender_name, target_groups, message_type='text'):
    """
    forward_message_to_groups 功能说明:
    # 将消息转发到指定的目标群列表，支持文本、图片和视频消息
    # 输入: wx(微信实例), message_content(str) - 消息内容或文件路径, sender_name(str) - 发送者名称, target_groups(list) - 目标群列表, message_type(str) - 消息类型 | 输出: None
    """
    try:
        success_count = 0
        for target_group in target_groups:
            try:
                # 切换到目标群聊天窗口
                wx.ChatWith(target_group)
                
                # 根据消息类型发送不同内容
                if message_type == 'text':
                    # 发送文本消息
                    wx.SendMsg(message_content)
                    log_info(f"文本消息已转发到群: {target_group}")
                elif message_type == 'image':
                    # 发送图片消息
                    # 确保路径是字符串格式（处理 WindowsPath 对象）
                    file_path = str(message_content)
                    if os.path.exists(file_path):
                        wx.SendFiles(file_path)
                        log_info(f"图片消息已转发到群: {target_group}")
                    else:
                        log_error(f"图片文件不存在: {file_path}")
                        continue
                elif message_type == 'video':
                    # 发送视频消息
                    # 确保路径是字符串格式（处理 WindowsPath 对象）
                    file_path = str(message_content)
                    if os.path.exists(file_path):
                        wx.SendFiles(file_path)
                        log_info(f"视频消息已转发到群: {target_group}")
                    else:
                        log_error(f"视频文件不存在: {file_path}")
                        continue
                else:
                    log_error(f"不支持的消息类型: {message_type}")
                    continue
                    
                success_count += 1
                # 添加短暂延迟避免发送过快
                time.sleep(0.5)
            except Exception as e:
                log_error(f"转发消息到群 {target_group} 失败: {str(e)}")
        
        log_info(f"消息转发完成，成功转发到 {success_count}/{len(target_groups)} 个群")
        
    except Exception as e:
        error_msg = f"转发消息时出现异常: {str(e)}\n{traceback.format_exc()}"
        log_error(error_msg)

def message_callback(msg, chat, wx, target_groups):
    """
    message_callback 功能说明:
    # 处理接收到的消息，转发文字、图片和视频类型消息到目标群
    # 输入: msg(消息对象), chat(聊天窗口对象), wx(微信实例), target_groups(list) - 目标群列表 | 输出: 无
    """
    try:
        log_info(f"收到来自 {msg.sender} 的消息: {msg.content}")
        log_info(f"消息类型: {msg.attr}")
        log_info(f"消息内容类型: {msg.type}")
        
        # 处理各种类型的消息
        if msg.type == 'text':
            # 转发文字类型消息
            log_info(f"检测到文字消息，开始转发: {msg.content}")
            
            # 检查消息内容是否有效
            if msg.content and msg.content.strip():
                # 转发消息到目标群
                forward_message_to_groups(wx, msg.content, msg.sender, target_groups, 'text')
            else:
                log_info(f"消息内容为空，跳过转发")
                
        elif msg.type == 'image':
            # 转发图片类型消息
            log_info(f"检测到图片消息，开始下载: {msg.content}")
            
            try:
                # 下载图片到本地临时文件
                download_result = msg.download()
                
                # 检查download()方法的返回值类型
                if isinstance(download_result, dict):
                    # 如果返回字典格式，检查状态
                    if download_result.get('status') == '失败':
                        error_msg = download_result.get('message', '未知错误')
                        log_error(f"图片下载失败: {error_msg}")
                        return
                    # 如果成功，获取实际路径
                    download_path = download_result.get('data')
                else:
                    # 如果返回字符串路径（旧版本兼容）
                    download_path = download_result
                
                # 验证下载路径
                if not download_path or not os.path.exists(download_path):
                    log_error(f"图片下载失败，路径无效: {download_path}")
                    return
                    
                log_info(f"图片下载成功: {download_path}")
                
                # 转发图片到目标群
                forward_message_to_groups(wx, download_path, msg.sender, target_groups, 'image')
                
                # 转发完成后删除临时文件
                try:
                    if os.path.exists(download_path):
                        os.remove(download_path)
                        log_info(f"已删除临时图片文件: {download_path}")
                except Exception as cleanup_e:
                    log_error(f"删除临时图片文件失败: {str(cleanup_e)}")
                    
            except Exception as e:
                log_error(f"处理图片消息异常: {str(e)}")
                
        elif msg.type == 'video':
            # 转发视频类型消息
            log_info(f"检测到视频消息，开始下载: {msg.content}")
            
            try:
                # 下载视频到本地临时文件（设置2分钟超时）
                def download_with_timeout():
                    return msg.download()
                
                # 使用线程池执行下载，设置120秒（2分钟）超时
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(download_with_timeout)
                    try:
                        download_result = future.result(timeout=120)
                    except concurrent.futures.TimeoutError:
                        log_error(f"视频下载超时: 下载时间超过2分钟")
                        return
                    except Exception as e:
                        log_error(f"视频下载异常: {str(e)}")
                        return
                
                # 检查download()方法的返回值类型
                if isinstance(download_result, dict):
                    # 如果返回字典格式，检查状态
                    if download_result.get('status') == '失败':
                        error_msg = download_result.get('message', '未知错误')
                        log_error(f"视频下载失败: {error_msg}")
                        return
                    # 如果成功，获取实际路径
                    download_path = download_result.get('data')
                else:
                    # 如果返回字符串路径（旧版本兼容）
                    download_path = download_result
                
                # 验证下载路径
                if not download_path or not os.path.exists(download_path):
                    log_error(f"视频下载失败，路径无效: {download_path}")
                    return
                    
                log_info(f"视频下载成功: {download_path}")
                
                # 转发视频到目标群
                forward_message_to_groups(wx, download_path, msg.sender, target_groups, 'video')
                
                # 转发完成后删除临时文件
                try:
                    if os.path.exists(download_path):
                        os.remove(download_path)
                        log_info(f"已删除临时视频文件: {download_path}")
                except Exception as cleanup_e:
                    log_error(f"删除临时视频文件失败: {str(cleanup_e)}")
                    
            except Exception as e:
                log_error(f"处理视频消息异常: {str(e)}")
                
        else:
            # 其他类型消息不转发
            log_info(f"不支持的消息类型: {msg.type}，跳过转发")
            
    except Exception as e:
        error_msg = f"处理消息时出现异常: {str(e)}\n{traceback.format_exc()}"
        log_error(error_msg)

def main():
    """
    main 功能说明:
    # 主程序入口，初始化微信实例并设置群消息转发监听
    # 输入: 无 | 输出: 无
    """
    try:
        log_info("=== 微信群消息转发程序启动 ===")
        
        # 加载转发配置
        config = load_forward_config()
        if not config['source_group'] or not config['target_groups']:
            log_error("转发配置无效，请检查配置文件")
            return
        
        # 初始化微信实例
        try:
            wx = WeChat()
            if wx is None:
                raise Exception("微信实例初始化失败，返回None")
            log_info("微信实例初始化成功")
        except Exception as e:
            error_msg = f"微信实例初始化失败: {str(e)}"
            log_error(error_msg)
            log_error("请确保：1. 微信已登录 2. 微信客户端正常运行")
            return
        log_info("lxg1}")
        # 为源群添加监听
        source_group = config['source_group']
        target_groups = config['target_groups']
        
        try:
            # 检查wx对象是否有效
            if not hasattr(wx, 'AddListenChat'):
                raise Exception("微信实例无效，缺少AddListenChat方法")
            log_info("lxg2}")

            # 创建带有目标群参数的回调函数
            def callback_with_params(msg, chat):
                message_callback(msg, chat, wx, target_groups)
            log_info("lxg3  call}")

            wx.AddListenChat(nickname=source_group, callback=callback_with_params)
            log_info(f"已添加监听源群: {source_group}")
            log_info(f"将转发到 {len(target_groups)} 个目标群: {', '.join(target_groups)}")
            log_info("lxg4 已添加监听源群}")

        except Exception as e:
            log_error(f"添加监听失败 {source_group}: {str(e)}")
            # 如果是关键错误，建议重新初始化
            if "NoneType" in str(e) or "NativeWindowHandle" in str(e):
                log_error("检测到微信实例异常，建议重启程序")
            return
        
        log_info("开始监听群消息并自动转发...")
        log_info("程序正在运行中，按 Ctrl+C 停止程序")
        
        # 保持程序运行
        if wx is not None and hasattr(wx, 'KeepRunning'):
            wx.KeepRunning()
        else:
            log_error("微信实例无效，无法保持运行状态")
            return
        
    except KeyboardInterrupt:
        log_info("用户手动停止程序")
    except Exception as e:
        error_msg = f"程序运行出错: {str(e)}\n{traceback.format_exc()}"
        log_error(error_msg)
    finally:
        log_info("=== 微信群消息转发程序结束 ===")

if __name__ == "__main__":
    main()