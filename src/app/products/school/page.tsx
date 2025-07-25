import Image from 'next/image';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CheckCircle, Users, BookUser, BarChart2, MessageSquare, Smartphone } from 'lucide-react';
import Link from 'next/link';
import { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from '@/components/ui/carousel';

const features = [
  { icon: <BookUser className="w-6 h-6 text-accent" />, text: 'Student registration & profiles' },
  { icon: <BarChart2 className="w-6 h-6 text-accent" />, text: 'Timetable & attendance' },
  { icon: <BarChart2 className="w-6 h-6 text-accent" />, text: 'Result computation & analytics' },
  { icon: <MessageSquare className="w-6 h-6 text-accent" />, text: 'Teacher-parent communication' },
  { icon: <Smartphone className="w-6 h-6 text-accent" />, text: 'Mobile-first experience' },
];

const benefits = [
    { for: 'Admins', description: 'Gain a complete overview of school operations, automate administrative tasks, and generate reports instantly.' },
    { for: 'Teachers', description: 'Easily manage attendance, input grades, and communicate with parents, saving valuable time.' },
    { for: 'Parents', description: 'Stay informed about your child’s progress, attendance, and school announcements through a dedicated portal.' },
]

const screenshots = [
  { src: 'https://firebasestudio.googleapis.com/v0/b/co-components-prod.appspot.com/o/images%2Fuser%2F1c37b848-a1c8-471a-942f-8796791f4b0f%2Fgenerated_1719597288673.png?alt=media&token=8e95793e-7a71-4603-9d95-8a2b53b84dd3', alt: 'Dashboard view', dataHint: 'dashboard analytics' },
  { src: 'https://placehold.co/1200x800', alt: 'Student Profile page', dataHint: 'student profile' },
  { src: 'https://placehold.co/1200x800', alt: 'Timetable management', dataHint: 'calendar schedule' },
  { src: 'https://placehold.co/1200x800', alt: 'Result analytics', dataHint: 'chart graph' },
  { src: 'https://placehold.co/1200x800', alt: 'Parent communication portal', dataHint: 'messaging app' },
];

export default function SchoolProductPage() {
  return (
    <>
      <section className="bg-secondary/50 py-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h1 className="font-headline text-4xl md:text-5xl font-bold text-primary">Simplify Every Aspect of School Operations</h1>
          <p className="mt-4 text-lg text-muted-foreground max-w-3xl mx-auto">
            The NestEdge School Management Engine is an all-in-one solution designed to streamline administrative tasks, enhance communication, and provide valuable insights for modern secondary schools.
          </p>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-12">
                <h2 className="font-headline text-3xl font-bold">Core Features</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                {features.map((feature, index) => (
                    <Card key={index} className="border-0 shadow-lg">
                        <CardContent className="pt-6">
                            <div className="flex items-center gap-4">
                                {feature.icon}
                                <span className="font-semibold text-foreground">{feature.text}</span>
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-secondary/50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
             <div className="text-center mb-12">
                <h2 className="font-headline text-3xl font-bold">See It In Action</h2>
                 <p className="mt-2 text-lg text-muted-foreground">Explore the intuitive interface of our school management platform.</p>
            </div>
            <Carousel className="w-full" opts={{ loop: true }}>
                <CarouselContent>
                    {screenshots.map((img, index) => (
                    <CarouselItem key={index}>
                        <Card className="overflow-hidden">
                            <CardContent className="p-0">
                                <Image
                                    src={img.src}
                                    alt={img.alt}
                                    width={1200}
                                    height={800}
                                    className="w-full h-auto object-cover"
                                    data-ai-hint={img.dataHint}
                                />
                            </CardContent>
                        </Card>
                    </CarouselItem>
                    ))}
                </CarouselContent>
                <CarouselPrevious className="ml-16" />
                <CarouselNext className="mr-16" />
            </Carousel>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="font-headline text-3xl font-bold">Benefits for Everyone</h2>
            <p className="mt-2 text-lg text-muted-foreground">A platform designed to empower every user in your school community.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {benefits.map((benefit) => (
              <Card key={benefit.for} className="text-center shadow-lg hover:shadow-xl transition-shadow">
                <CardHeader>
                  <CardTitle className="font-headline text-2xl flex items-center justify-center gap-2"><Users/> For {benefit.for}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-muted-foreground">{benefit.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-primary text-primary-foreground py-20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="font-headline text-3xl md:text-4xl font-bold">Ready to Transform Your School?</h2>
          <p className="text-lg opacity-80 mt-4 mb-8">
            Schedule a personalized demo or start a free trial to experience the power of NestEdge firsthand.
          </p>
          <Button size="lg" asChild className="bg-accent text-accent-foreground hover:bg-accent/90">
            <Link href="/demo">Request a Demo</Link>
          </Button>
        </div>
      </section>
    </>
  );
}
