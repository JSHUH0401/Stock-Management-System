create or replace function delivery_completed(
    p_order_id INT
)
returns void as $$
begin
    update "PURCHASE_ORDERS"
    set status = '배송완료'
    where order_id = p_order_id;

    update "PURCHASE_ITEMS"
    set status = '배송완료'
    where order_id = p_order_id;

    update "STOCKS" s
    set stock = s.stock + pi.actual_qty
    from "PURCHASE_ITEMS" pi
    where pi.order_id = p_order_id
    and s.item_id = pi.item_id;

exception when others then
raise exception '입고 처리 중 오류가 발생했습니다.%',sqlerrm;
end;
