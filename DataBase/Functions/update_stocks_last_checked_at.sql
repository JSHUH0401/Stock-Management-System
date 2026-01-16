--재고 업데이트 시 자동으로 현재 시각을 last_checked_at 칼럼에 추가
create trigger update_stocks_last_checked_at
before update on "STOCKS"
for each row
execute function update_last_checked_at_column();
