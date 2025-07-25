import { Hourglass } from 'lucide-react';

export default function DemoPage() {
  return (
    <>
      <section className="bg-primary text-primary-foreground py-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h1 className="font-headline text-4xl md:text-5xl font-bold">Product Demo</h1>
          <p className="mt-4 text-lg text-primary-foreground/80 max-w-3xl mx-auto">
            An interactive look at our platform is on its way.
          </p>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="flex flex-col items-center justify-center space-y-6">
            <Hourglass className="w-24 h-24 text-primary animate-spin" />
            <h2 className="font-headline text-3xl md:text-4xl font-bold text-foreground">Demo Coming Soon!</h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              We are working hard to bring you an interactive demo experience. Please check back shortly. In the meantime, you can contact us for more information.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
