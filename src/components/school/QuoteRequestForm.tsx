
"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { sendQuoteRequest } from "@/actions/send-quote-request";

const formSchema = z.object({
  schoolName: z.string().min(2, { message: "School name must be at least 2 characters." }),
  role: z.string().min(2, { message: "Role must be at least 2 characters." }),
  schoolAddress: z.string().min(10, { message: "Address must be at least 10 characters." }),
  schoolEmail: z.string().email({ message: "Please enter a valid email address." }),
});

interface QuoteRequestFormProps {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
}

export function QuoteRequestForm({ isOpen, onOpenChange }: QuoteRequestFormProps) {
  const { toast } = useToast();
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      schoolName: "",
      role: "",
      schoolAddress: "",
      schoolEmail: "",
    },
  });

  async function onSubmit(values: z.infer<typeof formSchema>) {
    const result = await sendQuoteRequest(values);

    if (result.success) {
      toast({
        title: "Quote Request Sent!",
        description: "Thank you for your interest. We will get back to you shortly with a detailed quote.",
      });
      form.reset();
      onOpenChange(false);
    } else {
      toast({
        variant: "destructive",
        title: "Submission Failed",
        description: result.error || "An unknown error occurred. Please try again.",
      });
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="font-headline">Request a Quote</DialogTitle>
          <DialogDescription>
            Please fill out the form below, and our team will get back to you with a personalized quote.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4 py-4">
            <FormField
              control={form.control}
              name="schoolName"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name of School</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g., Bright Future High" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Your Role in the School</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g., Principal, IT Administrator" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="schoolAddress"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Address of School</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g., 123 Education Lane, Knowledge City" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="schoolEmail"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email of School</FormLabel>
                  <FormControl>
                    <Input type="email" placeholder="e.g., contact@brightfuturehigh.edu" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
             <DialogFooter>
                <Button 
                    type="submit" 
                    className="w-full bg-accent text-accent-foreground hover:bg-accent/90" 
                    disabled={form.formState.isSubmitting}
                >
                    {form.formState.isSubmitting ? "Submitting..." : "Submit Request"}
                </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
