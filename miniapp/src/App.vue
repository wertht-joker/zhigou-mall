<script>
export default {
  onLaunch() {
    console.log('智购商城小程序启动')
  },
}
</script>

<style>
page {
  background: #f5f6f8;
  color: #1f2937;
  font-size: 28rpx;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Helvetica Neue', sans-serif;
}

view,
text,
image,
input,
button {
  box-sizing: border-box;
}

.card {
  background: #fff;
  border-radius: 24rpx;
}

.price {
  color: #e1251b;
  font-weight: 700;
}

.muted {
  color: #8a8f99;
}

.btn-primary {
  background: linear-gradient(120deg, #e1251b, #ff6a3d);
  color: #fff;
  border: none;
  border-radius: 999rpx;
  font-size: 28rpx;
  font-weight: 600;
}

.btn-primary::after {
  border: none;
}

.btn-ghost {
  background: #fff;
  color: #e1251b;
  border: 1rpx solid #f3b8b3;
  border-radius: 999rpx;
  font-size: 28rpx;
}

.btn-ghost::after {
  border: none;
}

.empty {
  padding: 120rpx 40rpx;
  text-align: center;
  color: #9aa0aa;
  font-size: 26rpx;
}
</style>
