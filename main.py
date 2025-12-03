import requests
import xml.etree.ElementTree as ET
import time
import statistics
from datetime import datetime
import concurrent.futures
import sys


class SitemapTester:
    def __init__(self, sitemap_url, max_workers=1, timeout=10):
        """
        初始化网站地图测试器

        Args:
            sitemap_url: 网站地图URL
            max_workers: 最大并发数，考虑到4M带宽，默认为1（顺序测试）
            timeout: 请求超时时间（秒）
        """
        self.sitemap_url = sitemap_url
        self.max_workers = max_workers
        self.timeout = timeout
        self.results = []
        self.session = requests.Session()
        # 设置合理的请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def parse_sitemap(self):
        """解析网站地图，提取所有URL"""
        try:
            print(f"正在获取网站地图: {self.sitemap_url}")
            response = self.session.get(self.sitemap_url, timeout=self.timeout)
            response.raise_for_status()

            # 解析XML
            root = ET.fromstring(response.content)

            # 命名空间处理
            namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

            urls = []
            for url in root.findall('ns:url', namespace):
                loc = url.find('ns:loc', namespace)
                if loc is not None:
                    urls.append(loc.text)

            print(f"成功解析 {len(urls)} 个URL")
            return urls

        except Exception as e:
            print(f"解析网站地图失败: {e}")
            return []

    def test_single_url(self, url):
        """测试单个URL的响应时间"""
        try:
            start_time = time.time()
            response = self.session.get(url, timeout=self.timeout)
            end_time = time.time()

            response_time = (end_time - start_time) * 1000  # 转换为毫秒

            result = {
                'url': url,
                'response_time': response_time,
                'status_code': response.status_code,
                'success': True,
                'error': None
            }

        except requests.exceptions.Timeout:
            result = {
                'url': url,
                'response_time': None,
                'status_code': None,
                'success': False,
                'error': '请求超时'
            }
        except Exception as e:
            result = {
                'url': url,
                'response_time': None,
                'status_code': None,
                'success': False,
                'error': str(e)
            }

        return result

    def run_test(self):
        """运行完整的测试"""
        print("开始测试网站地图中的页面...")
        print("=" * 60)

        # 解析网站地图
        urls = self.parse_sitemap()
        if not urls:
            print("没有找到可测试的URL")
            return

        # 测试每个URL
        print(f"\n开始测试 {len(urls)} 个页面 (并发数: {self.max_workers})")
        print("-" * 60)

        start_test_time = time.time()

        # 使用线程池控制并发数（考虑到带宽限制，建议max_workers=1）
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_url = {executor.submit(self.test_single_url, url): url for url in urls}

            # 处理完成的任务
            for i, future in enumerate(concurrent.futures.as_completed(future_to_url), 1):
                url = future_to_url[future]
                try:
                    result = future.result()
                    self.results.append(result)

                    # 实时显示进度
                    if result['success']:
                        print(f"{i:2d}/{len(urls)} ✓ {url} - {result['response_time']:.0f}ms")
                    else:
                        print(f"{i:2d}/{len(urls)} ✗ {url} - {result['error']}")

                    # 在请求之间添加延迟，避免对服务器造成压力
                    if self.max_workers == 1:
                        time.sleep(1)  # 顺序测试时添加1秒间隔

                except Exception as e:
                    print(f"{i:2d}/{len(urls)} ✗ {url} - 测试异常: {e}")

        total_test_time = time.time() - start_test_time
        print(f"\n测试完成! 总耗时: {total_test_time:.1f}秒")

        # 生成报告
        self.generate_report()

    def generate_report(self):
        """生成测试报告"""
        if not self.results:
            print("没有测试结果可报告")
            return

        successful_tests = [r for r in self.results if r['success']]
        failed_tests = [r for r in self.results if not r['success']]

        print("\n" + "=" * 60)
        print("测试结果摘要")
        print("=" * 60)
        print(f"总页面数: {len(self.results)}")
        print(f"成功测试: {len(successful_tests)}")
        print(f"失败测试: {len(failed_tests)}")

        if successful_tests:
            response_times = [r['response_time'] for r in successful_tests]

            print(f"\n响应时间统计 (毫秒):")
            print(f"  最快: {min(response_times):.0f}ms")
            print(f"  最慢: {max(response_times):.0f}ms")
            print(f"  平均: {statistics.mean(response_times):.0f}ms")
            print(f"  中位数: {statistics.median(response_times):.0f}ms")

            # 响应时间分布
            fast = len([t for t in response_times if t < 500])  # < 500ms
            medium = len([t for t in response_times if 500 <= t < 2000])  # 0.5-2秒
            slow = len([t for t in response_times if t >= 2000])  # > 2秒

            print(f"\n响应时间分布:")
            print(f"  < 500ms: {fast} 个页面 ({fast / len(successful_tests) * 100:.1f}%)")
            print(f"  500ms-2s: {medium} 个页面 ({medium / len(successful_tests) * 100:.1f}%)")
            print(f"  > 2s: {slow} 个页面 ({slow / len(successful_tests) * 100:.1f}%)")

        if failed_tests:
            print(f"\n失败页面详情:")
            for test in failed_tests:
                print(f"  {test['url']} - {test['error']}")

        # 保存详细结果到文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sitemap_test_results_{timestamp}.txt"

        with open(filename, 'w', encoding='utf-8') as f:
            f.write("网站地图响应时间测试报告\n")
            f.write(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"网站地图: {self.sitemap_url}\n")
            f.write(f"测试页面数: {len(self.results)}\n\n")

            for result in self.results:
                if result['success']:
                    f.write(f"✓ {result['url']} - {result['response_time']:.0f}ms\n")
                else:
                    f.write(f"✗ {result['url']} - {result['error']}\n")

        print(f"\n详细结果已保存到: {filename}")


def main():
    """主函数"""
    # 配置参数
    SITEMAP_URL = "https://xiaozou123.cn/sitemap-post-type-post.xml"  # 替换为实际的网站地图URL
    MAX_WORKERS = 1  # 考虑到4M带宽，使用顺序测试
    TIMEOUT = 15  # 请求超时时间（秒）

    # 创建测试器并运行测试
    tester = SitemapTester(
        sitemap_url=SITEMAP_URL,
        max_workers=MAX_WORKERS,
        timeout=TIMEOUT
    )

    try:
        tester.run_test()
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"测试过程中发生错误: {e}")


if __name__ == "__main__":
    main()