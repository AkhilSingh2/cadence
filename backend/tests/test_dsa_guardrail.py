from app.tools.dsa_tutor import looks_like_full_solution


def test_detects_python_solution():
    text = """
Here you go:
```python
class Solution:
    def invertTree(self, root):
        if not root:
            return None
        root.left, root.right = self.invertTree(root.right), self.invertTree(root.left)
        return root
```
"""
    assert looks_like_full_solution(text)


def test_allows_short_hint():
    text = "Check your base case when root is None before recursing on both children."
    assert not looks_like_full_solution(text)
