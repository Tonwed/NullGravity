"use client";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

interface PaymentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  type: "alipay" | "wechat";
}

export function PaymentDialog({ open, onOpenChange, type }: PaymentDialogProps) {
  const title = type === "alipay" ? "支付宝" : "微信支付";
  const imgSrc = type === "alipay" ? "/zfb.png" : "/wx.png";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[320px]">
        <DialogHeader>
          <DialogTitle className="text-center">{title}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col items-center py-4">
          <div className="w-64 h-64 rounded-lg overflow-hidden border bg-white">
            <img src={imgSrc} alt={title} className="w-full h-full object-contain" />
          </div>
          <p className="text-xs text-muted-foreground mt-4 text-center">
            扫描二维码进行赞助
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
