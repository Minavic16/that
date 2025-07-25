import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import Link from 'next/link';
import Image from 'next/image';
import { ArrowRight, CheckCircle, BookOpen, Home as HomeIcon, Users } from 'lucide-react';
import ProductCard from '@/components/shared/ProductCard';

export default function Home() {
  const benefits = [
    {
      icon: <BookOpen className="w-10 h-10 text-primary" />,
      title: 'Unified School Management',
      description: 'Centralize student data, timetables, and results with one seamless tool.',
    },
    {
      icon: <HomeIcon className="w-10 h-10 text-primary" />,
      title: 'Streamlined Real Estate',
      description: 'Manage listings, agents, and inquiries effortlessly on a modern platform.',
    },
    {
      icon: <Users className="w-10 h-10 text-primary" />,
      title: 'Enhanced Collaboration',
      description: 'Foster better communication between parents, teachers, agents, and clients.',
    },
     {
      icon: <CheckCircle className="w-10 h-10 text-primary" />,
      title: 'Data-Driven Insights',
      description: 'Leverage analytics to make informed decisions for your school or agency.',
    },
  ];

  const testimonials = [
    {
      name: 'Admin, Bright Future High',
      quote: 'NestEdge has revolutionized how we manage our school. Everything is in one place, and it’s incredibly intuitive.',
      avatar: 'BF',
      image: 'https://placehold.co/100x100'
    },
    {
      name: 'Jane Doe, Premium Properties',
      quote: 'The agent dashboard is a game-changer. I can track my listings and leads with ease. Highly recommended!',
      avatar: 'JD',
      image: 'https://placehold.co/100x100'
    },
  ];

  return (
    <div className="flex flex-col">
      <section className="relative h-[80vh] flex items-center justify-center text-center text-white bg-primary/90">
         <Image
          src="https://placehold.co/1600x900"
          alt="Abstract background"
          layout="fill"
          objectFit="cover"
          className="z-0 opacity-20"
          data-ai-hint="abstract texture"
        />
        <div className="relative z-10 p-4 max-w-4xl mx-auto">
          <h1 className="font-headline text-4xl md:text-6xl lg:text-7xl font-bold mb-4 animate-fade-in-down">
            Smart Platforms for Smarter Systems
          </h1>
          <p className="text-lg md:text-xl text-primary-foreground/80 mb-8 max-w-2xl mx-auto">
            NestEdge provides intelligent, scalable software to simplify education and real estate operations for the modern world.
          </p>
          <div className="flex justify-center gap-4">
            <Button asChild size="lg" className="bg-accent text-accent-foreground hover:bg-accent/90">
              <Link href="/products">Explore Products</Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="text-white border-white hover:bg-white hover:text-primary">
              <Link href="/demo">Request a Demo</Link>
            </Button>
          </div>
        </div>
      </section>

      <section id="about" className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="font-headline text-3xl md:text-4xl font-bold text-foreground mb-4">Who We Are</h2>
          <p className="text-lg text-muted-foreground max-w-3xl mx-auto">
            NestEdge is a forward-thinking software company, and a subsidiary of GMG, focused on transforming essential systems through intelligent platforms. From education to real estate, we create tools that make life simpler, more organized, and more connected.
          </p>
        </div>
      </section>

      <section id="products" className="py-16 md:py-24 bg-secondary/50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="font-headline text-3xl md:text-4xl font-bold text-foreground">Our Products</h2>
            <p className="text-lg text-muted-foreground mt-2">Two products. One platform. Built for real impact.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <ProductCard
              icon={<BookOpen className="w-12 h-12 text-primary" />}
              title="NestEdge School Management Engine"
              description="A powerful all-in-one tool for secondary school operations, from registration to result computation."
              link="/products/school"
            />
            <ProductCard
              icon={<HomeIcon className="w-12 h-12 text-primary" />}
              title="NestEstate"
              description="An intuitive platform for real estate listing, management, and sales, designed for agents and property seekers."
              link="/products/real-estate"
            />
          </div>
        </div>
      </section>

      <section id="benefits" className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="font-headline text-3xl md:text-4xl font-bold text-foreground">Transforming Industries</h2>
            <p className="text-lg text-muted-foreground mt-2">Key benefits that drive success across sectors.</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {benefits.map((benefit, index) => (
              <Card key={index} className="text-center p-6 border-0 shadow-lg hover:shadow-xl transition-shadow duration-300">
                <div className="flex justify-center mb-4">{benefit.icon}</div>
                <h3 className="font-headline text-xl font-semibold mb-2">{benefit.title}</h3>
                <p className="text-muted-foreground">{benefit.description}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>
      
      <section id="testimonials" className="py-16 md:py-24 bg-secondary/50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="font-headline text-3xl md:text-4xl font-bold text-foreground">Trusted by Leaders</h2>
             <p className="text-lg text-muted-foreground mt-2">Hear what our partners have to say about NestEdge.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {testimonials.map((testimonial, index) => (
              <Card key={index} className="bg-card">
                <CardContent className="pt-6">
                  <div className="flex items-start space-x-4">
                    <Avatar>
                      <AvatarImage src={testimonial.image} alt={testimonial.name} data-ai-hint="person portrait" />
                      <AvatarFallback>{testimonial.avatar}</AvatarFallback>
                    </Avatar>
                    <div className="flex-1">
                      <p className="text-lg italic text-foreground mb-4">"{testimonial.quote}"</p>
                      <p className="font-bold text-right font-headline text-primary">{testimonial.name}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>
      
      <section id="cta" className="py-16 md:py-24 bg-primary text-primary-foreground">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="font-headline text-3xl md:text-4xl font-bold">Ready to Elevate Your Systems?</h2>
          <p className="text-lg opacity-80 mt-4 mb-8">
            Let us show you how NestEdge can transform your operations. Get in touch with our team for a personalized demo.
          </p>
          <Button size="lg" variant="secondary" asChild className="bg-accent text-accent-foreground hover:bg-accent/90">
            <Link href="/demo">Request a Demo <ArrowRight className="ml-2 h-5 w-5" /></Link>
          </Button>
        </div>
      </section>
    </div>
  );
}
