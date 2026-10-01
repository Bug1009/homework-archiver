"""冒烟测试：保证包可导入、版本号合法。"""

import homework_archiver


def test_version_is_str():
    assert isinstance(homework_archiver.__version__, str)
    assert homework_archiver.__version__.count(".") == 2
